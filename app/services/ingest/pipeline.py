from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import uuid

from fastapi import UploadFile
from langchain_core.documents import Document

from app.core.config import Settings, get_settings
from app.integrations.mongodb_chunk_store import (
    ChunkBackupRecord,
    EmbeddingCacheRecord,
    MongoChunkStore,
)
from app.integrations.ollama_embeddings import OllamaEmbeddingsClient
from app.integrations.weaviate_client import ChunkRecord, RetrievedChunk, WeaviateClient
from app.schemas.ingest import (
    ClearKnowledgeBaseResponse,
    DeleteDocumentResponse,
    DocumentChunkPreview,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSummary,
    IngestFileResult,
    IngestResponse,
    PublishResponse,
)
from app.services.ingest.loaders import UnsupportedFileTypeError, load_text_from_bytes
from app.services.ingest.sanitizer import sanitize_text
from app.services.ingest.splitter import split_documents


class IngestService:
    def __init__(
        self,
        settings: Settings,
        embedding_client: OllamaEmbeddingsClient,
        weaviate_client: WeaviateClient,
        chunk_store: MongoChunkStore,
    ) -> None:
        self.settings = settings
        self.embedding_client = embedding_client
        self.weaviate_client = weaviate_client
        self.chunk_store = chunk_store

    @staticmethod
    def _is_embedding_too_long_error(error: ValueError) -> bool:
        return "embedding input is too long" in str(error).lower()

    async def _embed_single_chunk_with_retry(
        self,
        chunk: Document,
        depth: int = 0,
        max_depth: int = 3,
    ) -> tuple[list[Document], list[list[float]]]:
        provider, model = self._resolve_embedding_identity()
        text_hash = self._text_hash(chunk.page_content)
        cached_map = await self.chunk_store.list_embeddings_by_text_hashes(
            provider=provider,
            model=model,
            text_hashes=[text_hash],
        )
        cached = cached_map.get(text_hash)
        if cached is not None:
            return [chunk], [cached.vector]
        try:
            vector = await self.embedding_client.embed_query(chunk.page_content)
            now = datetime.now(timezone.utc).isoformat()
            await self.chunk_store.upsert_embeddings(
                [
                    EmbeddingCacheRecord(
                        embedding_key=self._embedding_key(provider, model, text_hash),
                        provider=provider,
                        model=model,
                        text_hash=text_hash,
                        vector=[float(value) for value in vector],
                        vector_dim=len(vector),
                        created_at=now,
                        updated_at=now,
                    )
                ]
            )
            return [chunk], [vector]
        except ValueError as exc:
            if not self._is_embedding_too_long_error(exc):
                raise
            if depth >= max_depth:
                raise ValueError(
                    "Embedding input remains too long after automatic rechunking. "
                    "Please reduce RAG_CHUNK_SIZE."
                ) from exc

            text = chunk.page_content
            child_chunk_size = max(120, len(text) // 2)
            child_chunk_overlap = min(
                self.settings.rag_chunk_overlap,
                max(0, child_chunk_size // 5),
            )
            if child_chunk_overlap >= child_chunk_size:
                child_chunk_overlap = max(0, child_chunk_size - 1)

            child_chunks = split_documents(
                documents=[chunk],
                chunk_size=child_chunk_size,
                chunk_overlap=child_chunk_overlap,
            )
            # Fallback to hard split when splitter cannot shrink further.
            if len(child_chunks) <= 1 and len(text) > 1:
                middle = len(text) // 2
                metadata = dict(chunk.metadata)
                child_chunks = [
                    Document(page_content=text[:middle], metadata=metadata),
                    Document(page_content=text[middle:], metadata=metadata),
                ]

            result_chunks: list[Document] = []
            result_vectors: list[list[float]] = []
            for child in child_chunks:
                if not child.page_content.strip():
                    continue
                embedded_chunks, embedded_vectors = await self._embed_single_chunk_with_retry(
                    child,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                result_chunks.extend(embedded_chunks)
                result_vectors.extend(embedded_vectors)
            return result_chunks, result_vectors

    async def _embed_chunks_with_fallback(
        self,
        chunks: list[Document],
    ) -> tuple[list[Document], list[list[float]]]:
        all_chunks: list[Document] = []
        all_vectors: list[list[float]] = []
        for chunk in chunks:
            embedded_chunks, embedded_vectors = await self._embed_single_chunk_with_retry(chunk)
            all_chunks.extend(embedded_chunks)
            all_vectors.extend(embedded_vectors)
        return all_chunks, all_vectors

    @staticmethod
    def _stable_chunk_id(document_id: str, index: int, text: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{index}:{text[:64]}"))

    def _resolve_embedding_identity(self) -> tuple[str, str]:
        provider = (self.settings.embedding_provider or "ollama").strip().lower() or "ollama"
        model = (self.settings.embedding_model or "").strip() or self.embedding_client.model
        return provider, model

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _embedding_key(provider: str, model: str, text_hash: str) -> str:
        return hashlib.sha256(f"{provider}:{model}:{text_hash}".encode("utf-8")).hexdigest()

    async def _resolve_vectors_with_cache(
        self,
        texts: list[str],
    ) -> tuple[list[list[float]], list[str], list[str], str, str]:
        if not texts:
            provider, model = self._resolve_embedding_identity()
            return [], [], [], provider, model

        provider, model = self._resolve_embedding_identity()
        text_hashes = [self._text_hash(text) for text in texts]
        cached_map = await self.chunk_store.list_embeddings_by_text_hashes(
            provider=provider,
            model=model,
            text_hashes=text_hashes,
        )

        miss_order: dict[str, str] = {}
        for text, text_hash in zip(texts, text_hashes):
            if text_hash in cached_map:
                continue
            if text_hash not in miss_order:
                miss_order[text_hash] = text

        if miss_order:
            miss_hashes = list(miss_order.keys())
            miss_texts = [miss_order[item] for item in miss_hashes]
            miss_vectors = await self.embedding_client.embed_texts(miss_texts)
            now = datetime.now(timezone.utc).isoformat()
            new_records: list[EmbeddingCacheRecord] = []
            for text_hash, vector in zip(miss_hashes, miss_vectors):
                embedding_key = self._embedding_key(provider, model, text_hash)
                record = EmbeddingCacheRecord(
                    embedding_key=embedding_key,
                    provider=provider,
                    model=model,
                    text_hash=text_hash,
                    vector=[float(value) for value in vector],
                    vector_dim=len(vector),
                    created_at=now,
                    updated_at=now,
                )
                cached_map[text_hash] = record
                new_records.append(record)
            await self.chunk_store.upsert_embeddings(new_records)

        vectors = [cached_map[text_hash].vector for text_hash in text_hashes]
        keys = [cached_map[text_hash].embedding_key for text_hash in text_hashes]
        return vectors, text_hashes, keys, provider, model

    async def _build_publish_records(
        self,
        draft_chunks: list[RetrievedChunk],
    ) -> tuple[list[ChunkRecord], list[ChunkBackupRecord]]:
        if not draft_chunks:
            return [], []
        vectors, text_hashes, embedding_keys, embedding_provider, embedding_model = await self._resolve_vectors_with_cache(
            [chunk.text for chunk in draft_chunks]
        )
        now = datetime.now(timezone.utc).isoformat()
        records: list[ChunkRecord] = []
        backups: list[ChunkBackupRecord] = []
        total = len(draft_chunks)
        for index, (chunk, vector, text_hash, embedding_key) in enumerate(
            zip(draft_chunks, vectors, text_hashes, embedding_keys)
        ):
            records.append(
                ChunkRecord(
                    chunk_id=self._stable_chunk_id(chunk.document_id, index, chunk.text),
                    document_id=chunk.document_id,
                    kb_version="publish",
                    text=chunk.text,
                    vector=vector,
                    source=chunk.source,
                    doc_hash=chunk.doc_hash,
                    chunk_index=index,
                    total_chunks=total,
                    ingested_at=now,
                )
            )
            backups.append(
                ChunkBackupRecord(
                    chunk_id=self._stable_chunk_id(chunk.document_id, index, chunk.text),
                    document_id=chunk.document_id,
                    kb_version="publish",
                    text=chunk.text,
                    source=chunk.source,
                    doc_hash=chunk.doc_hash,
                    chunk_index=index,
                    total_chunks=total,
                    ingested_at=now,
                    embedding_key=embedding_key,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    text_hash=text_hash,
                    embedding_dim=len(vector),
                )
            )
        return records, backups

    async def publish_document(self, document_id: str) -> PublishResponse:
        effective_id = document_id.strip()
        if not effective_id:
            raise ValueError("document_id is required.")

        draft_chunks = await self.weaviate_client.list_chunks_by_document_version(
            document_id=effective_id,
            kb_version="draft",
        )
        if not draft_chunks:
            raise ValueError("No draft chunks found for document_id.")

        publish_records, backup_records = await self._build_publish_records(draft_chunks)

        await self.weaviate_client.delete_chunks_by_document_version(effective_id, "publish")
        await self.chunk_store.delete_by_document_version(effective_id, "publish")
        await self.weaviate_client.upsert_chunks(publish_records)
        await self.chunk_store.upsert_chunks(backup_records)
        return PublishResponse(document_id=effective_id, chunks_published=len(publish_records))

    async def list_documents(self, kb_version: str | None = None) -> DocumentListResponse:
        summaries = await self.chunk_store.list_documents(kb_version=kb_version)
        items = [
            DocumentSummary(
                document_id=item.document_id,
                source=item.source,
                kb_version=item.kb_version,
                chunks=item.chunks,
                updated_at=item.updated_at,
            )
            for item in summaries
        ]
        return DocumentListResponse(items=items)

    async def get_document_detail(self, document_id: str, kb_version: str) -> DocumentDetailResponse:
        effective_id = document_id.strip()
        if not effective_id:
            raise ValueError("document_id is required.")
        chunk_items = await self.chunk_store.list_document_chunks(
            document_id=effective_id,
            kb_version=kb_version,
        )
        return DocumentDetailResponse(
            document_id=effective_id,
            kb_version=kb_version,
            chunks=[
                DocumentChunkPreview(
                    chunk_id=item.chunk_id,
                    chunk_index=item.chunk_index,
                    total_chunks=item.total_chunks,
                    source=item.source,
                    kb_version=item.kb_version,
                    doc_hash=item.doc_hash,
                    text=item.text,
                    ingested_at=item.ingested_at,
                )
                for item in chunk_items
            ],
        )

    async def delete_document(self, document_id: str, kb_version: str) -> DeleteDocumentResponse:
        effective_id = document_id.strip()
        if not effective_id:
            raise ValueError("document_id is required.")
        if kb_version not in {"draft", "publish", "all"}:
            raise ValueError("kb_version must be one of: draft, publish, all.")

        targets = ["draft", "publish"] if kb_version == "all" else [kb_version]
        weaviate_deleted = 0
        mongo_deleted = 0
        for target_version in targets:
            weaviate_deleted += await self.weaviate_client.delete_chunks_by_document_version(
                effective_id,
                target_version,
            )
            mongo_deleted += await self.chunk_store.delete_by_document_version(
                effective_id,
                target_version,
            )
        return DeleteDocumentResponse(
            document_id=effective_id,
            kb_version=kb_version,
            weaviate_deleted=weaviate_deleted,
            mongo_deleted=mongo_deleted,
        )

    async def clear_knowledge_base(self) -> ClearKnowledgeBaseResponse:
        weaviate_deleted = await self.weaviate_client.clear_all_chunks()
        mongo_deleted = await self.chunk_store.clear_all_chunks()
        return ClearKnowledgeBaseResponse(
            scope="all",
            weaviate_deleted=weaviate_deleted,
            mongo_deleted=mongo_deleted,
        )

    async def ingest_files(self, files: list[UploadFile], document_id: str | None = None) -> IngestResponse:
        results: list[IngestFileResult] = []
        total_chunks = 0
        if document_id and len(files) != 1:
            raise ValueError("When document_id is provided, exactly one file must be uploaded.")

        for upload_file in files:
            raw_bytes = await upload_file.read()
            if not raw_bytes:
                raise ValueError(f"File is empty: {upload_file.filename}")

            max_size = self.settings.ingest_max_file_size_mb * 1024 * 1024
            if len(raw_bytes) > max_size:
                raise ValueError(
                    f"File too large: {upload_file.filename}. "
                    f"Max allowed: {self.settings.ingest_max_file_size_mb} MB."
                )

            filename = upload_file.filename or "unknown"
            doc_hash = hashlib.sha256(raw_bytes).hexdigest()
            effective_document_id = document_id.strip() if document_id else str(uuid.uuid5(uuid.NAMESPACE_URL, doc_hash))

            try:
                raw_text = load_text_from_bytes(filename=filename, payload=raw_bytes)
            except UnsupportedFileTypeError as exc:
                raise ValueError(str(exc)) from exc

            clean_text = sanitize_text(raw_text)
            if not clean_text:
                raise ValueError(f"No extractable text: {filename}")

            base_doc = Document(
                page_content=clean_text,
                metadata={
                    "source": filename,
                    "doc_hash": doc_hash,
                    "document_id": effective_document_id,
                },
            )
            chunks = split_documents(
                documents=[base_doc],
                chunk_size=self.settings.rag_chunk_size,
                chunk_overlap=self.settings.rag_chunk_overlap,
            )
            chunks, vectors = await self._embed_chunks_with_fallback(chunks)
            embedding_provider, embedding_model = self._resolve_embedding_identity()

            ingested_at = datetime.now(timezone.utc).isoformat()
            records: list[ChunkRecord] = []
            backup_records: list[ChunkBackupRecord] = []
            for index, (chunk_doc, vector) in enumerate(zip(chunks, vectors)):
                chunk_id = self._stable_chunk_id(effective_document_id, index, chunk_doc.page_content)
                text_hash = self._text_hash(chunk_doc.page_content)
                embedding_key = self._embedding_key(embedding_provider, embedding_model, text_hash)
                records.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        document_id=effective_document_id,
                        kb_version="draft",
                        text=chunk_doc.page_content,
                        vector=vector,
                        source=filename,
                        doc_hash=doc_hash,
                        chunk_index=index,
                        total_chunks=len(chunks),
                        ingested_at=ingested_at,
                    )
                )
                backup_records.append(
                    ChunkBackupRecord(
                        chunk_id=chunk_id,
                        document_id=effective_document_id,
                        kb_version="draft",
                        text=chunk_doc.page_content,
                        source=filename,
                        doc_hash=doc_hash,
                        chunk_index=index,
                        total_chunks=len(chunks),
                        ingested_at=ingested_at,
                        embedding_key=embedding_key,
                        embedding_provider=embedding_provider,
                        embedding_model=embedding_model,
                        text_hash=text_hash,
                        embedding_dim=len(vector),
                    )
                )

            await self.weaviate_client.delete_chunks_by_document_version(effective_document_id, "draft")
            await self.chunk_store.delete_by_document_version(effective_document_id, "draft")
            await self.weaviate_client.upsert_chunks(records)
            await self.chunk_store.upsert_chunks(backup_records)

            results.append(
                IngestFileResult(
                    filename=filename,
                    document_id=effective_document_id,
                    kb_version="draft",
                    doc_hash=doc_hash,
                    chunks_indexed=len(records),
                )
            )
            total_chunks += len(records)

        return IngestResponse(
            total_files=len(results),
            total_chunks_indexed=total_chunks,
            results=results,
        )


@lru_cache
def get_ingest_service() -> IngestService:
    settings = get_settings()
    embedding_client = OllamaEmbeddingsClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embedding_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    weaviate_client = WeaviateClient(
        settings.weaviate_url,
        settings.weaviate_collection,
        settings.weaviate_api_key,
        settings.deepseek_timeout_seconds,
        settings.weaviate_grpc_host,
        settings.weaviate_grpc_port,
        settings.weaviate_grpc_secure,
    )
    chunk_store = MongoChunkStore(
        mongodb_uri=settings.mongodb_uri,
        db_name=settings.mongodb_db_name,
        collection_name=settings.mongodb_chunk_collection,
        embedding_collection_name=settings.mongodb_embedding_collection,
    )
    return IngestService(
        settings=settings,
        embedding_client=embedding_client,
        weaviate_client=weaviate_client,
        chunk_store=chunk_store,
    )
