import asyncio
from dataclasses import dataclass

import pytest

from app.integrations.mongodb_chunk_store import EmbeddingCacheRecord, MongoChunkStore

# pylint: disable=protected-access


@dataclass
class _DeleteResult:
    deleted_count: int


class _FakeCursor:
    def __init__(self, docs):  # type: ignore[no-untyped-def]
        self._docs = docs

    async def to_list(self, length: int):  # type: ignore[no-untyped-def]
        _ = length
        return self._docs


class _FakeEmbeddingCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.bulk_ops = None
        self.last_query = None

    def find(self, query, projection=None):  # type: ignore[no-untyped-def]
        _ = projection
        self.last_query = query
        provider = query.get("provider")
        model = query.get("model")
        text_hashes = set(query.get("text_hash", {}).get("$in", []))
        filtered = [
            item
            for item in self.docs
            if item.get("provider") == provider
            and item.get("model") == model
            and item.get("text_hash") in text_hashes
        ]
        return _FakeCursor(filtered)

    async def bulk_write(self, operations, ordered=False):  # type: ignore[no-untyped-def]
        _ = ordered
        self.bulk_ops = operations

    async def delete_many(self, query):  # type: ignore[no-untyped-def]
        _ = query
        count = len(self.docs)
        self.docs = []
        return _DeleteResult(deleted_count=count)

    async def create_index(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return "ok"


class _FakeChunkCollection:
    async def create_index(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return "ok"

    async def delete_many(self, query):  # type: ignore[no-untyped-def]
        _ = query
        return _DeleteResult(deleted_count=0)


def _make_store(embedding_collection: _FakeEmbeddingCollection) -> MongoChunkStore:
    store = MongoChunkStore.__new__(MongoChunkStore)
    store._chunk_collection = _FakeChunkCollection()
    store._embedding_collection = embedding_collection
    store._index_ready = True
    store._index_lock = asyncio.Lock()
    return store


@pytest.mark.asyncio
async def test_list_embeddings_by_text_hashes_returns_mapping() -> None:
    embedding_collection = _FakeEmbeddingCollection()
    embedding_collection.docs = [
        {
            "embedding_key": "k1",
            "provider": "ollama",
            "model": "m1",
            "text_hash": "h1",
            "vector": [0.1, 0.2],
            "vector_dim": 2,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    store = _make_store(embedding_collection)

    data = await store.list_embeddings_by_text_hashes("ollama", "m1", ["h1", "h2"])

    assert set(data.keys()) == {"h1"}
    assert data["h1"].embedding_key == "k1"
    assert data["h1"].vector == [0.1, 0.2]


@pytest.mark.asyncio
async def test_upsert_embeddings_builds_operations() -> None:
    embedding_collection = _FakeEmbeddingCollection()
    store = _make_store(embedding_collection)
    now = "2026-01-01T00:00:00+00:00"

    await store.upsert_embeddings(
        [
            EmbeddingCacheRecord(
                embedding_key="k1",
                provider="ollama",
                model="m1",
                text_hash="h1",
                vector=[0.3, 0.4],
                vector_dim=2,
                created_at=now,
                updated_at=now,
            )
        ]
    )

    assert embedding_collection.bulk_ops is not None
    assert len(embedding_collection.bulk_ops) == 1
    op = embedding_collection.bulk_ops[0]
    assert op._filter == {"provider": "ollama", "model": "m1", "text_hash": "h1"}  # type: ignore[attr-defined]
