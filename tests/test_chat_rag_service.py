from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.integrations.weaviate_client import RetrievedChunk
from app.services.rag.pipeline import ChatRagService
from app.services.rag.prompt_budget import PromptBudgetManager


@dataclass
class StubRewriteService:
    received_history: list[dict[str, str]] | None = None
    received_profile_context: str | None = None

    async def rewrite(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
        profile_context: str | None = None,
    ) -> str:
        _ = question
        self.received_history = history_messages
        self.received_profile_context = profile_context
        return "rewritten-question"


@dataclass
class StubRetrieverService:
    chunks: list[RetrievedChunk]
    called_count: int = 0

    async def retrieve(self, query: str, top_k: int, kb_version: str) -> list[RetrievedChunk]:
        _ = query, top_k, kb_version
        self.called_count += 1
        return self.chunks


@dataclass
class StubRerankerService:
    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        _ = query, top_n
        return candidates


@dataclass
class StubAnswerService:
    received_history: list[dict[str, str]] | None = None
    received_profile_context: str | None = None

    async def generate_answer(
        self,
        user_question: str,
        rewritten_query: str,
        context_chunks: list[RetrievedChunk],
        history_messages: list[dict[str, str]] | None = None,
        profile_context: str | None = None,
    ) -> str:
        _ = user_question, rewritten_query, context_chunks
        self.received_history = history_messages
        self.received_profile_context = profile_context
        return "final-answer"


@dataclass
class StubChatStore:
    history: list[dict[str, str]] = field(default_factory=list)
    append_calls: list[dict[str, object]] = field(default_factory=list)
    profile: dict[str, object] = field(default_factory=dict)
    profile_upsert_calls: list[dict[str, object]] = field(default_factory=list)
    should_fail_profile_upsert: bool = False

    async def get_recent_messages(
        self,
        session_id: str,
        limit_turns: int | None = None,
    ) -> list[dict[str, str]]:
        _ = session_id, limit_turns
        return self.history

    async def append_messages(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.append_calls.append(
            {
                "session_id": session_id,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "metadata": metadata,
            }
        )

    async def get_profile(self, session_id: str) -> dict[str, object]:
        _ = session_id
        return self.profile

    async def upsert_profile(self, session_id: str, patch: dict[str, object]) -> None:
        self.profile_upsert_calls.append({"session_id": session_id, "patch": patch})
        if self.should_fail_profile_upsert:
            raise RuntimeError("profile upsert failed")


@pytest.mark.asyncio
async def test_chat_service_uses_history_and_maps_source_fields() -> None:
    settings = SimpleNamespace(
        rag_enable_rewrite=True,
        rag_enable_rerank=False,
        rag_retrieval_top_k=8,
        rag_rerank_top_n=4,
        rag_history_max_turns=6,
        memory_enable=False,
        memory_profile_enable=False,
        memory_short_max_tokens=1200,
        memory_profile_max_items=6,
    )
    history = [{"role": "user", "content": "上一轮问题"}]
    store = StubChatStore(history=history)
    rewrite_service = StubRewriteService()
    answer_service = StubAnswerService()
    retriever_service = StubRetrieverService(
        chunks=[
            RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                kb_version="publish",
                text="chunk text",
                source="demo.md",
                doc_hash="hash",
                chunk_index=2,
                total_chunks=10,
                score=0.88,
            )
        ]
    )
    service = ChatRagService(
        settings=settings,
        rewrite_service=rewrite_service,
        retriever_service=retriever_service,
        reranker_service=StubRerankerService(),
        answer_service=answer_service,
        chat_store=store,
        prompt_budget_manager=PromptBudgetManager(),
    )

    result = await service.chat(
        question="当前问题",
        session_id="session-1",
        enable_rewrite=True,
        enable_rerank=False,
        kb_version="publish",
    )

    assert rewrite_service.received_history == history
    assert answer_service.received_history == history
    assert result.session_id == "session-1"
    assert result.answer == "final-answer"
    assert result.sources[0].chunk_index == 2
    assert result.sources[0].total_chunks == 10
    assert len(store.append_calls) == 1


@pytest.mark.asyncio
async def test_chat_service_generates_session_id_when_missing() -> None:
    settings = SimpleNamespace(
        rag_enable_rewrite=False,
        rag_enable_rerank=False,
        rag_retrieval_top_k=8,
        rag_rerank_top_n=4,
        rag_history_max_turns=6,
        memory_enable=False,
        memory_profile_enable=False,
        memory_short_max_tokens=1200,
        memory_profile_max_items=6,
    )
    store = StubChatStore(history=[])
    service = ChatRagService(
        settings=settings,
        rewrite_service=StubRewriteService(),
        retriever_service=StubRetrieverService(chunks=[]),
        reranker_service=StubRerankerService(),
        answer_service=StubAnswerService(),
        chat_store=store,
        prompt_budget_manager=PromptBudgetManager(),
    )

    result = await service.chat(
        question="没有结果的查询",
        session_id=None,
        enable_rewrite=False,
        enable_rerank=False,
        kb_version="publish",
    )

    assert result.session_id
    assert len(store.append_calls) == 1
    assert store.append_calls[0]["session_id"] == result.session_id


@pytest.mark.asyncio
async def test_chat_service_trims_history_and_passes_profile_context_when_memory_enabled() -> None:
    settings = SimpleNamespace(
        rag_enable_rewrite=True,
        rag_enable_rerank=False,
        rag_retrieval_top_k=8,
        rag_rerank_top_n=4,
        rag_history_max_turns=20,
        memory_enable=True,
        memory_profile_enable=True,
        memory_short_max_tokens=20,
        memory_profile_max_items=6,
    )
    history = [
        {"role": "user", "content": "第一轮问题，内容很长。" * 20},
        {"role": "assistant", "content": "第一轮回答，内容很长。" * 20},
        {"role": "user", "content": "第二轮问题，内容很长。" * 20},
        {"role": "assistant", "content": "第二轮回答，内容很长。" * 20},
    ]
    store = StubChatStore(
        history=history,
        profile={
            "language": "zh-CN",
            "style": "concise",
            "constraints": ["no_network"],
        },
    )
    rewrite_service = StubRewriteService()
    answer_service = StubAnswerService()
    retriever_service = StubRetrieverService(
        chunks=[
            RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                kb_version="publish",
                text="chunk text",
                source="demo.md",
                doc_hash="hash",
                chunk_index=0,
                total_chunks=1,
                score=0.8,
            )
        ]
    )
    budget_manager = PromptBudgetManager()
    service = ChatRagService(
        settings=settings,
        rewrite_service=rewrite_service,
        retriever_service=retriever_service,
        reranker_service=StubRerankerService(),
        answer_service=answer_service,
        chat_store=store,
        prompt_budget_manager=budget_manager,
    )

    result = await service.chat(
        question="请用中文简洁回答，不要联网。",
        session_id="session-1",
        enable_rewrite=True,
        enable_rerank=False,
        kb_version="publish",
    )

    assert result.answer == "final-answer"
    assert rewrite_service.received_history is not None
    assert len(rewrite_service.received_history) < len(history)
    assert rewrite_service.received_profile_context
    assert "Preferred language: zh-CN" in rewrite_service.received_profile_context
    assert "Constraints: no_network" in rewrite_service.received_profile_context
    assert answer_service.received_profile_context == rewrite_service.received_profile_context
    assert store.profile_upsert_calls


@pytest.mark.asyncio
async def test_chat_service_ignores_profile_update_failure() -> None:
    settings = SimpleNamespace(
        rag_enable_rewrite=False,
        rag_enable_rerank=False,
        rag_retrieval_top_k=8,
        rag_rerank_top_n=4,
        rag_history_max_turns=6,
        memory_enable=True,
        memory_profile_enable=True,
        memory_short_max_tokens=1200,
        memory_profile_max_items=6,
    )
    store = StubChatStore(
        history=[],
        profile={},
        should_fail_profile_upsert=True,
    )
    service = ChatRagService(
        settings=settings,
        rewrite_service=StubRewriteService(),
        retriever_service=StubRetrieverService(
            chunks=[
                RetrievedChunk(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    kb_version="publish",
                    text="chunk text",
                    source="demo.md",
                    doc_hash="hash",
                    chunk_index=0,
                    total_chunks=1,
                    score=0.8,
                )
            ]
        ),
        reranker_service=StubRerankerService(),
        answer_service=StubAnswerService(),
        chat_store=store,
        prompt_budget_manager=PromptBudgetManager(),
    )

    result = await service.chat(
        question="请用中文回答",
        session_id="session-1",
        enable_rewrite=False,
        enable_rerank=False,
        kb_version="publish",
    )

    assert result.answer == "final-answer"
    assert len(store.append_calls) == 1


@pytest.mark.asyncio
async def test_chat_service_filters_low_score_chunks_with_fallback_keep() -> None:
    settings = SimpleNamespace(
        rag_enable_rewrite=False,
        rag_enable_rerank=True,
        rag_retrieval_top_k=8,
        rag_rerank_top_n=4,
        rag_rerank_min_score=0.2,
        rag_min_chunks_keep=1,
        rag_history_max_turns=6,
        memory_enable=False,
        memory_profile_enable=False,
        memory_short_max_tokens=1200,
        memory_profile_max_items=6,
    )
    low_score_chunks = [
        RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            kb_version="publish",
            text="text-1",
            source="demo.md",
            doc_hash="hash",
            chunk_index=0,
            total_chunks=3,
            score=0.10,
        ),
        RetrievedChunk(
            chunk_id="chunk-2",
            document_id="doc-2",
            kb_version="publish",
            text="text-2",
            source="demo.md",
            doc_hash="hash",
            chunk_index=1,
            total_chunks=3,
            score=0.05,
        ),
        RetrievedChunk(
            chunk_id="chunk-3",
            document_id="doc-3",
            kb_version="publish",
            text="text-3",
            source="demo.md",
            doc_hash="hash",
            chunk_index=2,
            total_chunks=3,
            score=0.01,
        ),
    ]
    store = StubChatStore(history=[])
    retriever_service = StubRetrieverService(chunks=low_score_chunks)
    service = ChatRagService(
        settings=settings,
        rewrite_service=StubRewriteService(),
        retriever_service=retriever_service,
        reranker_service=StubRerankerService(),
        answer_service=StubAnswerService(),
        chat_store=store,
        prompt_budget_manager=PromptBudgetManager(),
    )

    result = await service.chat(
        question="测试低分过滤",
        session_id="session-1",
        enable_rewrite=False,
        enable_rerank=True,
        kb_version="publish",
    )

    assert result.answer == "final-answer"
    assert len(result.sources) == 1
    assert result.sources[0].chunk_id == "chunk-1"


@pytest.mark.asyncio
async def test_chat_service_returns_greeting_fallback_when_no_chunks() -> None:
    settings = SimpleNamespace(
        rag_enable_rewrite=False,
        rag_enable_rerank=False,
        rag_retrieval_top_k=8,
        rag_rerank_top_n=4,
        rag_history_max_turns=6,
        memory_enable=False,
        memory_profile_enable=False,
        memory_short_max_tokens=1200,
        memory_profile_max_items=6,
    )
    store = StubChatStore(history=[])
    retriever_service = StubRetrieverService(chunks=[])
    service = ChatRagService(
        settings=settings,
        rewrite_service=StubRewriteService(),
        retriever_service=retriever_service,
        reranker_service=StubRerankerService(),
        answer_service=StubAnswerService(),
        chat_store=store,
        prompt_budget_manager=PromptBudgetManager(),
    )

    result = await service.chat(
        question="hi",
        session_id="session-1",
        enable_rewrite=True,
        enable_rerank=False,
        kb_version="publish",
    )

    assert result.sources == []
    assert result.answer.startswith("你好，我在。")
    assert retriever_service.called_count == 0
