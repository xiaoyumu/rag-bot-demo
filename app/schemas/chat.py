from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    enable_rewrite: bool | None = None
    enable_rerank: bool | None = None
    kb_version: Literal["draft", "publish"] = "publish"


class ChatSource(BaseModel):
    chunk_id: str
    document_id: str | None = None
    kb_version: str | None = None
    source: str
    score: float | None = None
    text: str
    chunk_index: int | None = None
    total_chunks: int | None = None


class ChatResponse(BaseModel):
    answer: str
    question: str
    session_id: str
    rewritten_query: str | None = None
    sources: list[ChatSource]
