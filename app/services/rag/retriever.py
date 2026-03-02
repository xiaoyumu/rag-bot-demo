from app.integrations.ollama_embeddings import OllamaEmbeddingsClient
from app.integrations.weaviate_client import RetrievedChunk, WeaviateClient


class RetrieverService:
    def __init__(
        self,
        embedding_client: OllamaEmbeddingsClient,
        weaviate_client: WeaviateClient,
    ) -> None:
        self.embedding_client = embedding_client
        self.weaviate_client = weaviate_client

    async def retrieve(self, query: str, top_k: int, kb_version: str) -> list[RetrievedChunk]:
        vector = await self.embedding_client.embed_query(query)
        return await self.weaviate_client.search_by_vector(
            query_vector=vector,
            limit=top_k,
            kb_version=kb_version,
        )
