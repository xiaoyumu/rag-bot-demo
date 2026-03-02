import asyncio
from dataclasses import dataclass
from typing import Any

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:  # pragma: no cover - runtime guard for missing optional dependency
    AsyncIOMotorClient = None  # type: ignore[assignment]

from pymongo import UpdateOne


@dataclass
class ChunkBackupRecord:
    chunk_id: str
    document_id: str
    kb_version: str
    text: str
    source: str
    doc_hash: str
    chunk_index: int
    total_chunks: int
    ingested_at: str
    embedding_key: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    text_hash: str | None = None
    embedding_dim: int | None = None


@dataclass
class EmbeddingCacheRecord:
    embedding_key: str
    provider: str
    model: str
    text_hash: str
    vector: list[float]
    vector_dim: int
    created_at: str
    updated_at: str


@dataclass
class DocumentSummaryRecord:
    document_id: str
    source: str
    kb_version: str
    chunks: int
    updated_at: str | None


class MongoChunkStore:
    def __init__(
        self,
        mongodb_uri: str,
        db_name: str,
        collection_name: str,
        embedding_collection_name: str = "kb_embeddings",
    ) -> None:
        if AsyncIOMotorClient is None:
            raise RuntimeError("motor is required for MongoChunkStore. Install it via `pip install motor`.")
        self._client = AsyncIOMotorClient(mongodb_uri)
        self._chunk_collection = self._client[db_name][collection_name]
        self._embedding_collection = self._client[db_name][embedding_collection_name]
        self._index_ready = False
        self._index_lock = asyncio.Lock()

    async def create_indexes(self) -> None:
        if self._index_ready:
            return
        async with self._index_lock:
            if self._index_ready:
                return
            await self._chunk_collection.create_index([("chunk_id", 1)], unique=True, name="chunk_id_unique_idx")
            await self._chunk_collection.create_index(
                [("document_id", 1), ("kb_version", 1), ("chunk_index", 1)],
                name="document_version_chunk_idx",
            )
            await self._chunk_collection.create_index([("embedding_key", 1)], name="chunk_embedding_key_idx")
            await self._embedding_collection.create_index(
                [("embedding_key", 1)],
                unique=True,
                name="embedding_key_unique_idx",
            )
            await self._embedding_collection.create_index(
                [("provider", 1), ("model", 1), ("text_hash", 1)],
                unique=True,
                name="provider_model_text_hash_unique_idx",
            )
            self._index_ready = True

    async def delete_by_document_version(self, document_id: str, kb_version: str) -> int:
        if not document_id:
            return 0
        await self.create_indexes()
        result = await self._chunk_collection.delete_many(
            {
                "document_id": document_id,
                "kb_version": kb_version,
            }
        )
        return int(result.deleted_count)

    async def upsert_chunks(self, chunks: list[ChunkBackupRecord]) -> None:
        if not chunks:
            return
        await self.create_indexes()
        operations: list[UpdateOne] = []
        for chunk in chunks:
            operations.append(
                UpdateOne(
                    {"chunk_id": chunk.chunk_id},
                    {
                        "$set": {
                            "document_id": chunk.document_id,
                            "kb_version": chunk.kb_version,
                            "text": chunk.text,
                            "source": chunk.source,
                            "doc_hash": chunk.doc_hash,
                            "chunk_index": chunk.chunk_index,
                            "total_chunks": chunk.total_chunks,
                            "ingested_at": chunk.ingested_at,
                            "embedding_key": chunk.embedding_key,
                            "embedding_provider": chunk.embedding_provider,
                            "embedding_model": chunk.embedding_model,
                            "text_hash": chunk.text_hash,
                            "embedding_dim": chunk.embedding_dim,
                        }
                    },
                    upsert=True,
                )
            )
        await self._chunk_collection.bulk_write(operations, ordered=False)

    async def list_embeddings_by_text_hashes(
        self,
        provider: str,
        model: str,
        text_hashes: list[str],
    ) -> dict[str, EmbeddingCacheRecord]:
        if not text_hashes:
            return {}
        await self.create_indexes()
        cursor = self._embedding_collection.find(
            {
                "provider": provider,
                "model": model,
                "text_hash": {"$in": list(set(text_hashes))},
            },
            projection={
                "_id": False,
                "embedding_key": True,
                "provider": True,
                "model": True,
                "text_hash": True,
                "vector": True,
                "vector_dim": True,
                "created_at": True,
                "updated_at": True,
            },
        )
        docs = await cursor.to_list(length=max(1, len(text_hashes)))
        result: dict[str, EmbeddingCacheRecord] = {}
        for doc in docs:
            text_hash = str(doc.get("text_hash", ""))
            vector = doc.get("vector")
            if not text_hash or not isinstance(vector, list):
                continue
            result[text_hash] = EmbeddingCacheRecord(
                embedding_key=str(doc.get("embedding_key", "")),
                provider=str(doc.get("provider", "")),
                model=str(doc.get("model", "")),
                text_hash=text_hash,
                vector=[float(value) for value in vector],
                vector_dim=int(doc.get("vector_dim", len(vector))),
                created_at=str(doc.get("created_at", "")),
                updated_at=str(doc.get("updated_at", "")),
            )
        return result

    async def upsert_embeddings(self, embeddings: list[EmbeddingCacheRecord]) -> None:
        if not embeddings:
            return
        await self.create_indexes()
        operations: list[UpdateOne] = []
        for item in embeddings:
            operations.append(
                UpdateOne(
                    {
                        "provider": item.provider,
                        "model": item.model,
                        "text_hash": item.text_hash,
                    },
                    {
                        "$set": {
                            "embedding_key": item.embedding_key,
                            "vector": item.vector,
                            "vector_dim": item.vector_dim,
                            "updated_at": item.updated_at,
                        },
                        "$setOnInsert": {
                            "created_at": item.created_at,
                            "provider": item.provider,
                            "model": item.model,
                            "text_hash": item.text_hash,
                        },
                    },
                    upsert=True,
                )
            )
        await self._embedding_collection.bulk_write(operations, ordered=False)

    async def list_documents(self, kb_version: str | None = None) -> list[DocumentSummaryRecord]:
        await self.create_indexes()
        match_stage: dict[str, Any] = {}
        if kb_version:
            match_stage["kb_version"] = kb_version

        pipeline: list[dict[str, Any]] = []
        if match_stage:
            pipeline.append({"$match": match_stage})
        pipeline.extend(
            [
                {
                    "$group": {
                        "_id": {
                            "document_id": "$document_id",
                            "kb_version": "$kb_version",
                        },
                        "source": {"$first": "$source"},
                        "chunks": {"$sum": 1},
                        "updated_at": {"$max": "$ingested_at"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "document_id": "$_id.document_id",
                        "kb_version": "$_id.kb_version",
                        "source": "$source",
                        "chunks": "$chunks",
                        "updated_at": "$updated_at",
                    }
                },
                {"$sort": {"updated_at": -1, "document_id": 1, "kb_version": 1}},
            ]
        )

        docs = await self._chunk_collection.aggregate(pipeline).to_list(length=1000)
        return [
            DocumentSummaryRecord(
                document_id=str(doc.get("document_id", "")),
                source=str(doc.get("source", "")),
                kb_version=str(doc.get("kb_version", "")),
                chunks=int(doc.get("chunks", 0)),
                updated_at=str(doc.get("updated_at")) if doc.get("updated_at") is not None else None,
            )
            for doc in docs
            if doc.get("document_id")
        ]

    async def list_document_chunks(
        self,
        document_id: str,
        kb_version: str,
        limit: int = 200,
    ) -> list[ChunkBackupRecord]:
        if not document_id:
            return []
        await self.create_indexes()
        cursor = self._chunk_collection.find(
            {"document_id": document_id, "kb_version": kb_version},
            projection={
                "_id": False,
                "chunk_id": True,
                "document_id": True,
                "kb_version": True,
                "text": True,
                "source": True,
                "doc_hash": True,
                "chunk_index": True,
                "total_chunks": True,
                "ingested_at": True,
                "embedding_key": True,
                "embedding_provider": True,
                "embedding_model": True,
                "text_hash": True,
                "embedding_dim": True,
            },
        ).sort("chunk_index", 1).limit(max(1, limit))
        docs = await cursor.to_list(length=max(1, limit))
        return [
            ChunkBackupRecord(
                chunk_id=str(doc.get("chunk_id", "")),
                document_id=str(doc.get("document_id", "")),
                kb_version=str(doc.get("kb_version", "")),
                text=str(doc.get("text", "")),
                source=str(doc.get("source", "")),
                doc_hash=str(doc.get("doc_hash", "")),
                chunk_index=int(doc.get("chunk_index", 0)),
                total_chunks=int(doc.get("total_chunks", 0)),
                ingested_at=str(doc.get("ingested_at", "")),
                embedding_key=str(doc.get("embedding_key")) if doc.get("embedding_key") is not None else None,
                embedding_provider=(
                    str(doc.get("embedding_provider")) if doc.get("embedding_provider") is not None else None
                ),
                embedding_model=str(doc.get("embedding_model")) if doc.get("embedding_model") is not None else None,
                text_hash=str(doc.get("text_hash")) if doc.get("text_hash") is not None else None,
                embedding_dim=int(doc.get("embedding_dim")) if doc.get("embedding_dim") is not None else None,
            )
            for doc in docs
            if doc.get("chunk_id")
        ]

    async def clear_all_chunks(self) -> int:
        await self.create_indexes()
        chunk_result = await self._chunk_collection.delete_many({})
        embedding_result = await self._embedding_collection.delete_many({})
        return int(chunk_result.deleted_count) + int(embedding_result.deleted_count)
