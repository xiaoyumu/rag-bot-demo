import logging
import re
from functools import lru_cache
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.integrations.deepseek_llm import DeepSeekClient
from app.integrations.mongodb_chat_store import MongoChatStore
from app.integrations.ollama_embeddings import OllamaEmbeddingsClient
from app.integrations.weaviate_client import RetrievedChunk, WeaviateClient
from app.schemas.chat import ChatResponse, ChatSource
from app.services.rag.chains import AnswerGenerationService
from app.services.rag.profile_memory import extract_profile_patch, render_profile_context
from app.services.rag.prompt_budget import PromptBudgetManager
from app.services.rag.reranker import FlashRankRerankerService
from app.services.rag.retriever import RetrieverService
from app.services.rag.rewrite import QuestionRewriteService

logger = logging.getLogger(__name__)


class ChatRagService:
    def __init__(
        self,
        settings: Settings,
        rewrite_service: QuestionRewriteService,
        retriever_service: RetrieverService,
        reranker_service: FlashRankRerankerService,
        answer_service: AnswerGenerationService,
        chat_store: MongoChatStore,
        prompt_budget_manager: PromptBudgetManager,
    ) -> None:
        self.settings = settings
        self.rewrite_service = rewrite_service
        self.retriever_service = retriever_service
        self.reranker_service = reranker_service
        self.answer_service = answer_service
        self.chat_store = chat_store
        self.prompt_budget_manager = prompt_budget_manager

    async def chat(
        self,
        question: str,
        session_id: str | None,
        enable_rewrite: bool | None,
        enable_rerank: bool | None,
        kb_version: str,
    ) -> ChatResponse:
        effective_session_id = session_id.strip() if session_id and session_id.strip() else str(uuid4())
        use_rewrite = self.settings.rag_enable_rewrite if enable_rewrite is None else enable_rewrite
        use_rerank = self.settings.rag_enable_rerank if enable_rerank is None else enable_rerank
        if self._is_greeting_query(question):
            fallback_answer = self._build_no_context_answer(question=question)
            rewritten_query = question if use_rewrite else None
            await self.chat_store.append_messages(
                session_id=effective_session_id,
                user_message=question,
                assistant_message=fallback_answer,
                metadata={"rewritten_query": rewritten_query, "sources": []},
            )
            return ChatResponse(
                answer=fallback_answer,
                question=question,
                session_id=effective_session_id,
                rewritten_query=rewritten_query,
                sources=[],
            )

        memory_enabled = bool(getattr(self.settings, "memory_enable", False))
        memory_profile_enabled = bool(getattr(self.settings, "memory_profile_enable", False))
        short_max_tokens = int(getattr(self.settings, "memory_short_max_tokens", 1200))
        profile_max_items = int(getattr(self.settings, "memory_profile_max_items", 6))
        history_messages = await self.chat_store.get_recent_messages(
            session_id=effective_session_id,
            limit_turns=self.settings.rag_history_max_turns,
        )
        original_history_count = len(history_messages)
        original_history_tokens = self._estimate_history_tokens(history_messages)
        profile_context = ""
        if memory_enabled:
            history_messages = self.prompt_budget_manager.trim_history(
                messages=history_messages,
                max_tokens=short_max_tokens,
            )
            trimmed_history_count = len(history_messages)
            trimmed_history_tokens = self._estimate_history_tokens(history_messages)
            logger.info(
                "memory_history_trimmed session_id=%s count_before=%d count_after=%d tokens_before=%d tokens_after=%d max_tokens=%d",
                effective_session_id,
                original_history_count,
                trimmed_history_count,
                original_history_tokens,
                trimmed_history_tokens,
                short_max_tokens,
            )
            if memory_profile_enabled:
                await self._update_profile_from_question(
                    session_id=effective_session_id,
                    question=question,
                )
                profile = await self._load_profile(session_id=effective_session_id)
                profile_context = render_profile_context(
                    profile=profile,
                    max_items=profile_max_items,
                )
                profile_item_count = len(
                    [line for line in profile_context.splitlines() if line.strip()]
                )
                logger.info(
                    "memory_profile_loaded session_id=%s profile_items=%d context_chars=%d",
                    effective_session_id,
                    profile_item_count,
                    len(profile_context),
                )

        rewritten_query = question
        if use_rewrite:
            rewritten_query = await self.rewrite_service.rewrite(
                question=question,
                history_messages=history_messages,
                profile_context=profile_context,
            )

        retrieved_chunks = await self.retriever_service.retrieve(
            query=rewritten_query,
            top_k=self.settings.rag_retrieval_top_k,
            kb_version=kb_version,
        )
        selected_chunks = self._select_chunks(
            query=rewritten_query,
            candidates=retrieved_chunks,
            use_rerank=use_rerank,
        )

        if not selected_chunks:
            fallback_answer = self._build_no_context_answer(question=question)
            await self.chat_store.append_messages(
                session_id=effective_session_id,
                user_message=question,
                assistant_message=fallback_answer,
                metadata={"rewritten_query": rewritten_query if use_rewrite else None, "sources": []},
            )
            return ChatResponse(
                answer=fallback_answer,
                question=question,
                session_id=effective_session_id,
                rewritten_query=rewritten_query if use_rewrite else None,
                sources=[],
            )

        answer = await self.answer_service.generate_answer(
            user_question=question,
            rewritten_query=rewritten_query,
            context_chunks=selected_chunks,
            history_messages=history_messages,
            profile_context=profile_context,
        )
        response_sources = [
            ChatSource(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                kb_version=chunk.kb_version,
                source=chunk.source,
                score=chunk.score,
                text=chunk.text,
                chunk_index=chunk.chunk_index,
                total_chunks=chunk.total_chunks,
            )
            for chunk in selected_chunks
        ]
        await self.chat_store.append_messages(
            session_id=effective_session_id,
            user_message=question,
            assistant_message=answer,
            metadata={
                "rewritten_query": rewritten_query if use_rewrite else None,
                "sources": [source.model_dump() for source in response_sources],
            },
        )
        return ChatResponse(
            answer=answer,
            question=question,
            session_id=effective_session_id,
            rewritten_query=rewritten_query if use_rewrite else None,
            sources=response_sources,
        )

    def _select_chunks(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        use_rerank: bool,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        if use_rerank:
            reranked = self.reranker_service.rerank(
                query=query,
                candidates=candidates,
                top_n=self.settings.rag_rerank_top_n,
            )
            if reranked:
                filtered = self._apply_rerank_score_filter(reranked)
                self._log_rerank_scores(
                    query=query,
                    chunks=filtered,
                    stage="after_rerank_filter",
                )
                return filtered
        fallback_chunks = self._apply_rerank_score_filter(candidates[: self.settings.rag_rerank_top_n])
        self._log_rerank_scores(
            query=query,
            chunks=fallback_chunks,
            stage="vector_fallback_selection",
        )
        return fallback_chunks

    def _apply_rerank_score_filter(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []

        min_score = float(getattr(self.settings, "rag_rerank_min_score", 0.0))
        min_keep = max(0, int(getattr(self.settings, "rag_min_chunks_keep", 1)))
        if min_score <= 0:
            return chunks

        filtered = [chunk for chunk in chunks if chunk.score is None or chunk.score >= min_score]
        removed_count = len(chunks) - len(filtered)
        if removed_count <= 0:
            return chunks

        logger.info(
            "rag_low_score_chunks_filtered removed=%d total=%d min_score=%.4f",
            removed_count,
            len(chunks),
            min_score,
        )
        if filtered:
            return filtered

        if min_keep <= 0:
            return []

        keep_count = min(min_keep, len(chunks))
        logger.info(
            "rag_low_score_filter_fallback keep_count=%d total=%d min_score=%.4f",
            keep_count,
            len(chunks),
            min_score,
        )
        return chunks[:keep_count]

    def _build_no_context_answer(self, question: str) -> str:
        if self._is_greeting_query(question):
            return (
                "你好，我在。当前知识库里没有可用参考内容。"
                "你可以直接告诉我具体问题，我会继续检索并回答。"
            )

        return (
            "我暂时没在知识库里检索到可用参考内容。"
            "你可以补充关键词、文档名或更具体的问题，例如“总结某文档的核心观点”。"
        )

    def _is_greeting_query(self, question: str) -> bool:
        normalized = re.sub(r"\s+", " ", question.strip().lower())
        greetings = {
            "hi",
            "hello",
            "hey",
            "你好",
            "您好",
            "哈喽",
            "在吗",
            "在么",
        }
        return normalized in greetings

    def _log_rerank_scores(self, query: str, chunks: list[RetrievedChunk], stage: str) -> None:
        if not bool(getattr(self.settings, "rag_log_rerank_scores", True)):
            return
        if not chunks:
            return

        scored_values = [float(chunk.score) for chunk in chunks if chunk.score is not None]
        if not scored_values:
            return

        max_items = max(1, int(getattr(self.settings, "rag_rerank_score_log_max_items", 3)))
        preview = []
        for chunk in chunks[:max_items]:
            source = (chunk.source or "unknown").split("/")[-1].split("\\")[-1]
            score_value = "n/a" if chunk.score is None else f"{float(chunk.score):.4f}"
            preview.append(f"{source}:{score_value}")
        query_preview = query.strip().replace("\n", " ")
        if len(query_preview) > 80:
            query_preview = f"{query_preview[:77]}..."

        avg_score = sum(scored_values) / len(scored_values)
        logger.info(
            "rag_rerank_score_snapshot stage=%s count=%d scored=%d min=%.4f max=%.4f avg=%.4f top=%s query=%s",
            stage,
            len(chunks),
            len(scored_values),
            min(scored_values),
            max(scored_values),
            avg_score,
            ",".join(preview),
            query_preview,
        )

    async def _update_profile_from_question(self, session_id: str, question: str) -> None:
        if not hasattr(self.chat_store, "upsert_profile"):
            return
        patch = extract_profile_patch(question)
        if not patch:
            return
        try:
            await self.chat_store.upsert_profile(session_id=session_id, patch=patch)
            logger.info(
                "memory_profile_updated session_id=%s patch_keys=%s",
                session_id,
                sorted(patch.keys()),
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("memory_profile_update_failed session_id=%s", session_id)
            return

    async def _load_profile(self, session_id: str) -> dict[str, object]:
        if not hasattr(self.chat_store, "get_profile"):
            return {}
        try:
            profile = await self.chat_store.get_profile(session_id=session_id)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("memory_profile_load_failed session_id=%s", session_id)
            return {}
        return profile if isinstance(profile, dict) else {}

    def _estimate_history_tokens(self, history_messages: list[dict[str, str]]) -> int:
        return sum(
            self.prompt_budget_manager.estimate_tokens_for_message(item)
            for item in history_messages
        )


@lru_cache
def get_chat_rag_service() -> ChatRagService:
    settings = get_settings()
    llm_client = DeepSeekClient(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_chat_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
    )
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

    rewrite_service = QuestionRewriteService(llm_client=llm_client)
    retriever_service = RetrieverService(
        embedding_client=embedding_client,
        weaviate_client=weaviate_client,
    )
    reranker_service = FlashRankRerankerService(
        model_name=settings.flashrank_model_name,
        cache_dir=settings.flashrank_cache_dir,
        offline_only=settings.flashrank_offline_only,
        max_passage_chars=settings.flashrank_max_passage_chars,
    )
    answer_service = AnswerGenerationService(llm_client=llm_client)
    chat_store = MongoChatStore(
        mongodb_uri=settings.mongodb_uri,
        db_name=settings.mongodb_db_name,
        collection_name=settings.mongodb_chat_collection,
        profile_collection_name=settings.mongodb_profile_collection,
        default_max_turns=settings.rag_history_max_turns,
    )
    prompt_budget_manager = PromptBudgetManager()

    return ChatRagService(
        settings=settings,
        rewrite_service=rewrite_service,
        retriever_service=retriever_service,
        reranker_service=reranker_service,
        answer_service=answer_service,
        chat_store=chat_store,
        prompt_budget_manager=prompt_budget_manager,
    )
