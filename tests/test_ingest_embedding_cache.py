from dataclasses import dataclass, field
import hashlib
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.integrations.mongodb_chunk_store import ChunkBackupRecord, EmbeddingCacheRecord
from app.integrations.weaviate_client import ChunkRecord, RetrievedChunk
from app.services.ingest.pipeline import IngestService

# pylint: disable=protected-access


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embedding_key(provider: str, model: str, text_hash: str) -> str:
    return hashlib.sha256(f"{provider}:{model}:{text_hash}".encode("utf-8")).hexdigest()


@dataclass
class StubEmbeddingClient:
    model: str = "nomic-embed-text-v2-moe:latest"
    embed_query_calls: int = 0
    embed_texts_calls: list[list[str]] = field(default_factory=list)

    async def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls += 1
        return [float(len(text)), 0.5]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embed_texts_calls.append(texts)
        return [[float(len(text)), 1.0] for text in texts]


@dataclass
class StubWeaviateClient:
    draft_chunks: list[RetrievedChunk] = field(default_factory=list)
    deleted_calls: list[tuple[str, str]] = field(default_factory=list)
    upserted_chunks: list[ChunkRecord] = field(default_factory=list)

    async def list_chunks_by_document_version(self, document_id: str, kb_version: str) -> list[RetrievedChunk]:
        _ = document_id, kb_version
        return self.draft_chunks

    async def delete_chunks_by_document_version(self, document_id: str, kb_version: str) -> int:
        self.deleted_calls.append((document_id, kb_version))
        return 1

    async def upsert_chunks(self, chunks: list[ChunkRecord]) -> None:
        self.upserted_chunks = chunks


@dataclass
class StubChunkStore:
    cached_embeddings: dict[str, EmbeddingCacheRecord] = field(default_factory=dict)
    upserted_embeddings: list[EmbeddingCacheRecord] = field(default_factory=list)
    upserted_chunks: list[ChunkBackupRecord] = field(default_factory=list)
    deleted_calls: list[tuple[str, str]] = field(default_factory=list)

    async def list_embeddings_by_text_hashes(
        self,
        provider: str,
        model: str,
        text_hashes: list[str],
    ) -> dict[str, EmbeddingCacheRecord]:
        _ = provider, model
        return {item: self.cached_embeddings[item] for item in text_hashes if item in self.cached_embeddings}

    async def upsert_embeddings(self, embeddings: list[EmbeddingCacheRecord]) -> None:
        self.upserted_embeddings.extend(embeddings)
        for item in embeddings:
            self.cached_embeddings[item.text_hash] = item

    async def delete_by_document_version(self, document_id: str, kb_version: str) -> int:
        self.deleted_calls.append((document_id, kb_version))
        return 1

    async def upsert_chunks(self, chunks: list[ChunkBackupRecord]) -> None:
        self.upserted_chunks = chunks


def _make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        rag_chunk_overlap=200,
        embedding_provider="ollama",
        embedding_model="nomic-embed-text-v2-moe:latest",
    )


@pytest.mark.asyncio
async def test_embed_single_chunk_uses_cache_without_calling_embedding_provider() -> None:
    embedding_client = StubEmbeddingClient()
    weaviate_client = StubWeaviateClient()
    chunk_store = StubChunkStore()
    service = IngestService(_make_settings(), embedding_client, weaviate_client, chunk_store)

    text = "cached-chunk"
    text_hash = _text_hash(text)
    chunk_store.cached_embeddings[text_hash] = EmbeddingCacheRecord(
        embedding_key=_embedding_key("ollama", "nomic-embed-text-v2-moe:latest", text_hash),
        provider="ollama",
        model="nomic-embed-text-v2-moe:latest",
        text_hash=text_hash,
        vector=[0.1, 0.2],
        vector_dim=2,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    chunks, vectors = await service._embed_single_chunk_with_retry(Document(page_content=text))

    assert len(chunks) == 1
    assert vectors == [[0.1, 0.2]]
    assert embedding_client.embed_query_calls == 0


@pytest.mark.asyncio
async def test_embed_single_chunk_miss_writes_embedding_cache() -> None:
    embedding_client = StubEmbeddingClient()
    weaviate_client = StubWeaviateClient()
    chunk_store = StubChunkStore()
    service = IngestService(_make_settings(), embedding_client, weaviate_client, chunk_store)

    text = "new-chunk"
    _, vectors = await service._embed_single_chunk_with_retry(Document(page_content=text))

    assert embedding_client.embed_query_calls == 1
    assert vectors == [[float(len(text)), 0.5]]
    assert len(chunk_store.upserted_embeddings) == 1
    item = chunk_store.upserted_embeddings[0]
    assert item.provider == "ollama"
    assert item.model == "nomic-embed-text-v2-moe:latest"
    assert item.text_hash == _text_hash(text)


@pytest.mark.asyncio
async def test_publish_document_reuses_cached_embeddings_and_persists_metadata() -> None:
    embedding_client = StubEmbeddingClient()
    draft_chunks = [
        RetrievedChunk(
            chunk_id="c1",
            document_id="doc-1",
            kb_version="draft",
            text="cached text",
            source="demo.md",
            doc_hash="h1",
            chunk_index=0,
            total_chunks=3,
        ),
        RetrievedChunk(
            chunk_id="c2",
            document_id="doc-1",
            kb_version="draft",
            text="new text",
            source="demo.md",
            doc_hash="h1",
            chunk_index=1,
            total_chunks=3,
        ),
        RetrievedChunk(
            chunk_id="c3",
            document_id="doc-1",
            kb_version="draft",
            text="new text",
            source="demo.md",
            doc_hash="h1",
            chunk_index=2,
            total_chunks=3,
        ),
    ]
    weaviate_client = StubWeaviateClient(draft_chunks=draft_chunks)
    chunk_store = StubChunkStore()
    service = IngestService(_make_settings(), embedding_client, weaviate_client, chunk_store)

    cached_hash = _text_hash("cached text")
    chunk_store.cached_embeddings[cached_hash] = EmbeddingCacheRecord(
        embedding_key=_embedding_key("ollama", "nomic-embed-text-v2-moe:latest", cached_hash),
        provider="ollama",
        model="nomic-embed-text-v2-moe:latest",
        text_hash=cached_hash,
        vector=[0.9, 0.8],
        vector_dim=2,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    result = await service.publish_document("doc-1")

    assert result.document_id == "doc-1"
    assert result.chunks_published == 3
    assert embedding_client.embed_texts_calls == [["new text"]]
    assert len(chunk_store.upserted_embeddings) == 1
    assert len(weaviate_client.upserted_chunks) == 3
    assert len(chunk_store.upserted_chunks) == 3
    assert all(item.embedding_provider == "ollama" for item in chunk_store.upserted_chunks)
    assert all(item.embedding_model == "nomic-embed-text-v2-moe:latest" for item in chunk_store.upserted_chunks)
    assert all(item.embedding_key for item in chunk_store.upserted_chunks)
