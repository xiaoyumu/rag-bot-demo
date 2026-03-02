from pydantic import BaseModel, Field


class IngestFileResult(BaseModel):
    filename: str
    document_id: str
    kb_version: str
    doc_hash: str
    chunks_indexed: int = Field(ge=0)


class IngestResponse(BaseModel):
    total_files: int = Field(ge=0)
    total_chunks_indexed: int = Field(ge=0)
    results: list[IngestFileResult]


class PublishResponse(BaseModel):
    document_id: str
    chunks_published: int = Field(ge=0)
    kb_version: str = "publish"


class DocumentSummary(BaseModel):
    document_id: str
    source: str
    kb_version: str
    chunks: int = Field(ge=0)
    updated_at: str | None = None


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]


class DocumentChunkPreview(BaseModel):
    chunk_id: str
    chunk_index: int = Field(ge=0)
    total_chunks: int = Field(ge=0)
    source: str
    kb_version: str
    doc_hash: str
    text: str
    ingested_at: str | None = None


class DocumentDetailResponse(BaseModel):
    document_id: str
    kb_version: str
    chunks: list[DocumentChunkPreview]


class DeleteDocumentResponse(BaseModel):
    document_id: str
    kb_version: str
    weaviate_deleted: int = Field(ge=0)
    mongo_deleted: int = Field(ge=0)


class ClearKnowledgeBaseResponse(BaseModel):
    scope: str = "all"
    weaviate_deleted: int = Field(ge=0)
    mongo_deleted: int = Field(ge=0)
