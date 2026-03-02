import logging

from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag.pipeline import get_chat_rag_service

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        service = get_chat_rag_service()
        return await service.chat(
            question=payload.question,
            session_id=payload.session_id,
            enable_rewrite=payload.enable_rewrite,
            enable_rerank=payload.enable_rerank,
            kb_version=payload.kb_version,
        )
    except ValueError as exc:
        logger.exception("Chat validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Chat pipeline failed.") from exc
