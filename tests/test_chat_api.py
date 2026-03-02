from dataclasses import dataclass

from fastapi.testclient import TestClient

import app.api.routes.chat as chat_route
from app.main import app
from app.schemas.chat import ChatResponse


@dataclass
class StubChatService:
    received_kb_version: str | None = None

    async def chat(
        self,
        question: str,
        session_id: str | None,
        enable_rewrite: bool | None,
        enable_rerank: bool | None,
        kb_version: str,
    ) -> ChatResponse:
        _ = session_id, enable_rewrite, enable_rerank
        self.received_kb_version = kb_version
        return ChatResponse(
            answer="stub answer",
            question=question,
            session_id="stub-session",
            rewritten_query="stub rewrite",
            sources=[],
        )


@dataclass
class StatefulStubChatService:
    turn: int = 0

    async def chat(
        self,
        question: str,
        session_id: str | None,
        enable_rewrite: bool | None,
        enable_rerank: bool | None,
        kb_version: str,
    ) -> ChatResponse:
        _ = enable_rewrite, enable_rerank, kb_version
        self.turn += 1
        return ChatResponse(
            answer=f"turn-{self.turn}",
            question=question,
            session_id=session_id or "generated-session",
            rewritten_query=None,
            sources=[],
        )


def test_chat_endpoint_returns_structured_payload(monkeypatch) -> None:
    stub_service = StubChatService()

    def _stub_factory() -> StubChatService:
        return stub_service

    monkeypatch.setattr(chat_route, "get_chat_rag_service", _stub_factory)
    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "question": "什么是 RAG？",
            "enable_rewrite": True,
            "enable_rerank": True,
            "kb_version": "draft",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "stub answer"
    assert payload["question"] == "什么是 RAG？"
    assert payload["session_id"] == "stub-session"
    assert payload["rewritten_query"] == "stub rewrite"
    assert payload["sources"] == []
    assert stub_service.received_kb_version == "draft"


def test_chat_endpoint_handles_long_session_sequence(monkeypatch) -> None:
    stub_service = StatefulStubChatService()

    def _stub_factory() -> StatefulStubChatService:
        return stub_service

    monkeypatch.setattr(chat_route, "get_chat_rag_service", _stub_factory)
    client = TestClient(app)

    session_id = "long-session-1"
    for i in range(35):
        response = client.post(
            "/api/chat",
            json={
                "question": f"第{i + 1}轮问题",
                "session_id": session_id,
                "enable_rewrite": True,
                "enable_rerank": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["session_id"] == session_id
        assert payload["question"] == f"第{i + 1}轮问题"
        assert payload["answer"] == f"turn-{i + 1}"
