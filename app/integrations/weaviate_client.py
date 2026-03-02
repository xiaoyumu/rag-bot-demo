import asyncio
from dataclasses import dataclass
import re
from urllib.parse import urlparse

from weaviate import WeaviateClient as NativeWeaviateClient
from weaviate.auth import AuthApiKey
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.connect import ConnectionParams


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    kb_version: str
    text: str
    vector: list[float]
    source: str
    doc_hash: str
    chunk_index: int
    total_chunks: int
    ingested_at: str


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    kb_version: str
    text: str
    source: str
    doc_hash: str
    chunk_index: int
    total_chunks: int
    distance: float | None = None
    score: float | None = None


class WeaviateClient:
    def __init__(
        self,
        base_url: str,
        collection: str,
        api_key: str = "",
        timeout_seconds: int = 60,
        grpc_host: str = "localhost",
        grpc_port: int = 50051,
        grpc_secure: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.grpc_host = grpc_host
        self.grpc_port = grpc_port
        self.grpc_secure = grpc_secure
        self._ensured = False
        self._client: NativeWeaviateClient | None = None
        self._ensure_lock = asyncio.Lock()

    def _safe_collection(self) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.collection):
            raise ValueError("Invalid Weaviate collection name.")
        return self.collection

    def _build_client(self) -> NativeWeaviateClient:
        parsed = urlparse(self.base_url)
        http_host = parsed.hostname or "localhost"
        http_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        http_secure = parsed.scheme == "https"

        connection_params = ConnectionParams.from_params(
            http_host=http_host,
            http_port=http_port,
            http_secure=http_secure,
            grpc_host=self.grpc_host or http_host,
            grpc_port=self.grpc_port,
            grpc_secure=self.grpc_secure,
        )
        auth_secret = AuthApiKey(self.api_key) if self.api_key else None
        client = NativeWeaviateClient(
            connection_params=connection_params,
            auth_client_secret=auth_secret,
        )
        client.connect()
        return client

    def _get_client(self) -> NativeWeaviateClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def ensure_collection(self) -> None:
        if self._ensured:
            return
        async with self._ensure_lock:
            if self._ensured:
                return
            await asyncio.to_thread(self._ensure_collection_sync)
            self._ensured = True

    def _ensure_collection_sync(self) -> None:
        collection = self._safe_collection()
        client = self._get_client()
        if client.collections.exists(collection):
            target = client.collections.get(collection)
            config = target.config.get(simple=True)
            existing_props = {
                prop.name
                for prop in (config.properties or [])
            }
            expected_props = [
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="kb_version", data_type=DataType.TEXT),
                Property(name="text", data_type=DataType.TEXT),
                Property(name="source", data_type=DataType.TEXT),
                Property(name="doc_hash", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="total_chunks", data_type=DataType.INT),
                Property(name="ingested_at", data_type=DataType.TEXT),
            ]
            for prop in expected_props:
                if prop.name not in existing_props:
                    target.config.add_property(prop)
            return
        client.collections.create(
            name=collection,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="kb_version", data_type=DataType.TEXT),
                Property(name="text", data_type=DataType.TEXT),
                Property(name="source", data_type=DataType.TEXT),
                Property(name="doc_hash", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="total_chunks", data_type=DataType.INT),
                Property(name="ingested_at", data_type=DataType.TEXT),
            ],
        )

    async def upsert_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return

        await self.ensure_collection()
        await asyncio.to_thread(self._upsert_chunks_sync, chunks)

    def _upsert_chunks_sync(self, chunks: list[ChunkRecord]) -> None:
        client = self._get_client()
        collection = client.collections.get(self.collection)
        with collection.batch.dynamic() as batch:
            for chunk in chunks:
                batch.add_object(
                    uuid=chunk.chunk_id,
                    properties={
                        "document_id": chunk.document_id,
                        "kb_version": chunk.kb_version,
                        "text": chunk.text,
                        "source": chunk.source,
                        "doc_hash": chunk.doc_hash,
                        "chunk_index": chunk.chunk_index,
                        "total_chunks": chunk.total_chunks,
                        "ingested_at": chunk.ingested_at,
                    },
                    vector=chunk.vector,
                )

    async def delete_chunks_by_document_version(self, document_id: str, kb_version: str) -> int:
        if not document_id:
            return 0
        await self.ensure_collection()
        return await asyncio.to_thread(self._delete_chunks_by_document_version_sync, document_id, kb_version)

    def _delete_chunks_by_document_version_sync(self, document_id: str, kb_version: str) -> int:
        client = self._get_client()
        collection = client.collections.get(self.collection)
        where = Filter.all_of(
            [
                Filter.by_property("document_id").equal(document_id),
                Filter.by_property("kb_version").equal(kb_version),
            ]
        )
        result = collection.data.delete_many(where=where)
        return int(getattr(result, "matches", 0))

    async def list_chunks_by_document_version(self, document_id: str, kb_version: str) -> list[RetrievedChunk]:
        if not document_id:
            return []
        await self.ensure_collection()
        return await asyncio.to_thread(self._list_chunks_by_document_version_sync, document_id, kb_version)

    def _list_chunks_by_document_version_sync(
        self,
        document_id: str,
        kb_version: str,
    ) -> list[RetrievedChunk]:
        client = self._get_client()
        collection = client.collections.get(self.collection)
        where = Filter.all_of(
            [
                Filter.by_property("document_id").equal(document_id),
                Filter.by_property("kb_version").equal(kb_version),
            ]
        )
        response = collection.query.fetch_objects(
            filters=where,
            limit=10000,
            return_properties=[
                "document_id",
                "kb_version",
                "text",
                "source",
                "doc_hash",
                "chunk_index",
                "total_chunks",
            ],
        )
        results: list[RetrievedChunk] = []
        for item in response.objects:
            properties = item.properties or {}
            results.append(
                RetrievedChunk(
                    chunk_id=str(item.uuid),
                    document_id=str(properties.get("document_id", "")),
                    kb_version=str(properties.get("kb_version", "")),
                    text=str(properties.get("text", "")),
                    source=str(properties.get("source", "")),
                    doc_hash=str(properties.get("doc_hash", "")),
                    chunk_index=int(properties.get("chunk_index", 0)),
                    total_chunks=int(properties.get("total_chunks", 0)),
                )
            )
        return sorted(results, key=lambda item: item.chunk_index)

    async def search_by_vector(
        self,
        query_vector: list[float],
        limit: int,
        kb_version: str = "publish",
    ) -> list[RetrievedChunk]:
        if limit <= 0:
            return []

        await self.ensure_collection()
        return await asyncio.to_thread(self._search_by_vector_sync, query_vector, limit, kb_version)

    def _search_by_vector_sync(
        self,
        query_vector: list[float],
        limit: int,
        kb_version: str,
    ) -> list[RetrievedChunk]:
        client = self._get_client()
        collection = client.collections.get(self.collection)
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            filters=Filter.by_property("kb_version").equal(kb_version),
            return_metadata=MetadataQuery(distance=True),
            return_properties=[
                "document_id",
                "kb_version",
                "text",
                "source",
                "doc_hash",
                "chunk_index",
                "total_chunks",
            ],
        )

        results: list[RetrievedChunk] = []
        for item in response.objects:
            properties = item.properties or {}
            metadata = item.metadata
            distance = getattr(metadata, "distance", None) if metadata else None
            results.append(
                RetrievedChunk(
                    chunk_id=str(item.uuid),
                    document_id=str(properties.get("document_id", "")),
                    kb_version=str(properties.get("kb_version", "")),
                    text=str(properties.get("text", "")),
                    source=str(properties.get("source", "")),
                    doc_hash=str(properties.get("doc_hash", "")),
                    chunk_index=int(properties.get("chunk_index", 0)),
                    total_chunks=int(properties.get("total_chunks", 0)),
                    distance=float(distance) if distance is not None else None,
                )
            )
        return results

    async def clear_all_chunks(self) -> int:
        await self.ensure_collection()
        return await asyncio.to_thread(self._clear_all_chunks_sync)

    def _clear_all_chunks_sync(self) -> int:
        client = self._get_client()
        collection = client.collections.get(self.collection)
        result = collection.data.delete_many(
            where=Filter.by_property("chunk_index").greater_or_equal(0),
        )
        return int(getattr(result, "matches", 0))
