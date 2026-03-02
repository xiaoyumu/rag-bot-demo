import logging

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile

from app.schemas.ingest import (
    ClearKnowledgeBaseResponse,
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    IngestResponse,
    PublishResponse,
)
from app.services.ingest.pipeline import get_ingest_service

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}


@router.post("/files", response_model=IngestResponse)
async def ingest_files(
    files: list[UploadFile],
    document_id: str | None = Form(default=None),
) -> IngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    for file in files:
        lower_name = (file.filename or "").lower()
        if not any(lower_name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.filename}",
            )

    try:
        service = get_ingest_service()
        return await service.ingest_files(files, document_id=document_id)
    except ValueError as exc:
        logger.exception("Ingest validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ingest unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Ingest failed.") from exc


@router.post("/documents/{document_id}/publish", response_model=PublishResponse)
async def publish_document(document_id: str) -> PublishResponse:
    try:
        service = get_ingest_service()
        return await service.publish_document(document_id=document_id)
    except ValueError as exc:
        logger.exception("Publish validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Publish unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Publish failed.") from exc


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    kb_version: str | None = Query(default=None),
) -> DocumentListResponse:
    if kb_version is not None and kb_version not in {"draft", "publish"}:
        raise HTTPException(status_code=400, detail="kb_version must be one of: draft, publish.")
    try:
        service = get_ingest_service()
        return await service.list_documents(kb_version=kb_version)
    except ValueError as exc:
        logger.exception("List documents validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("List documents unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="List documents failed.") from exc


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: str,
    kb_version: str = Query(default="draft"),
) -> DocumentDetailResponse:
    if kb_version not in {"draft", "publish"}:
        raise HTTPException(status_code=400, detail="kb_version must be one of: draft, publish.")
    try:
        service = get_ingest_service()
        return await service.get_document_detail(document_id=document_id, kb_version=kb_version)
    except ValueError as exc:
        logger.exception("Document detail validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Document detail unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Get document detail failed.") from exc


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    document_id: str,
    kb_version: str = Query(default="all"),
) -> DeleteDocumentResponse:
    if kb_version not in {"draft", "publish", "all"}:
        raise HTTPException(status_code=400, detail="kb_version must be one of: draft, publish, all.")
    try:
        service = get_ingest_service()
        return await service.delete_document(document_id=document_id, kb_version=kb_version)
    except ValueError as exc:
        logger.exception("Delete document validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Delete document unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Delete document failed.") from exc


@router.delete("/documents", response_model=ClearKnowledgeBaseResponse)
async def clear_knowledge_base(
    confirm_text: str = Query(...),
) -> ClearKnowledgeBaseResponse:
    if confirm_text != "CLEAR ALL":
        raise HTTPException(status_code=400, detail="Invalid confirm_text. Use: CLEAR ALL")
    try:
        service = get_ingest_service()
        return await service.clear_knowledge_base()
    except ValueError as exc:
        logger.exception("Clear knowledge base validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Clear knowledge base unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Clear knowledge base failed.") from exc
