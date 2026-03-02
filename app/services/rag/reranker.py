from pathlib import Path

from flashrank import Ranker, RerankRequest

from app.integrations.weaviate_client import RetrievedChunk


class FlashRankRerankerService:
    def __init__(
        self,
        model_name: str = "ms-marco-MiniLM-L-12-v2",
        cache_dir: str = ".cache/flashrank",
        offline_only: bool = True,
        max_passage_chars: int = 1200,
    ) -> None:
        model_dir = Path(cache_dir) / model_name
        if offline_only and not model_dir.exists():
            raise RuntimeError(
                "FlashRank model is not preloaded for offline mode. "
                f"Expected directory: {model_dir}"
            )
        self.ranker = Ranker(model_name=model_name, cache_dir=cache_dir)
        self.max_passage_chars = max(100, int(max_passage_chars))

    def rerank(self, query: str, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        if not candidates or top_n <= 0:
            return []

        passages = [
            {
                "id": candidate.chunk_id or str(index),
                "text": self._build_passage_text(candidate),
            }
            for index, candidate in enumerate(candidates)
        ]
        request = RerankRequest(query=query, passages=passages)
        ranked = self.ranker.rerank(request)

        candidate_by_id: dict[str, RetrievedChunk] = {}
        for index, candidate in enumerate(candidates):
            candidate_by_id[candidate.chunk_id or str(index)] = candidate

        reordered: list[RetrievedChunk] = []
        for item in ranked[:top_n]:
            chunk_id = str(item.get("id", ""))
            original = candidate_by_id.get(chunk_id)
            if not original:
                continue
            original.score = float(item.get("score", 0.0))
            reordered.append(original)
        return reordered

    def _build_passage_text(self, candidate: RetrievedChunk) -> str:
        source = candidate.source.strip() if candidate.source else ""
        content = candidate.text.strip()
        if source:
            combined = f"source: {source}\ncontent: {content}"
        else:
            combined = content
        if len(combined) <= self.max_passage_chars:
            return combined
        return combined[: self.max_passage_chars]
