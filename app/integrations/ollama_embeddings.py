import logging

import httpx

logger = logging.getLogger(__name__)


class OllamaEmbeddingsClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text,
                    },
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    response_text = exc.response.text.strip()
                    if "input length exceeds the context length" in response_text.lower():
                        raise ValueError(
                            "Embedding input is too long for current Ollama model. "
                            "Please reduce RAG_CHUNK_SIZE."
                        ) from exc
                    logger.error(
                        "Ollama embeddings request failed: status=%s model=%s body=%s",
                        exc.response.status_code,
                        self.model,
                        response_text[:500],
                    )
                    raise ValueError("Embedding request failed from Ollama API.") from exc
                payload = response.json()
                embedding = payload.get("embedding")
                if not isinstance(embedding, list):
                    raise ValueError("Invalid embedding payload from Ollama API.")
                vectors.append([float(value) for value in embedding])
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]
