from fastapi.testclient import TestClient

import app.api.routes.ingest as ingest_route
from app.main import app
from app.schemas.ingest import (
    ClearKnowledgeBaseResponse,
    DeleteDocumentResponse,
    DocumentChunkPreview,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSummary,
    IngestFileResult,
    IngestResponse,
    PublishResponse,
)


def test_ingest_rejects_unsupported_file_type() -> None:
    client = TestClient(app)
    files = [("files", ("demo.csv", b"a,b\n1,2", "text/csv"))]
    response = client.post("/api/ingest/files", files=files)
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_ingest_passes_document_id_to_service(monkeypatch) -> None:
    class StubIngestService:
        async def ingest_files(self, files, document_id=None):  # type: ignore[no-untyped-def]
            _ = files
            assert document_id == "doc-123"
            return IngestResponse(
                total_files=1,
                total_chunks_indexed=2,
                results=[
                    IngestFileResult(
                        filename="demo.md",
                        document_id="doc-123",
                        kb_version="draft",
                        doc_hash="hash",
                        chunks_indexed=2,
                    )
                ],
            )

    def _stub_factory() -> StubIngestService:
        return StubIngestService()

    monkeypatch.setattr(ingest_route, "get_ingest_service", _stub_factory)
    client = TestClient(app)
    files = [("files", ("demo.md", b"# title\ncontent", "text/markdown"))]
    response = client.post("/api/ingest/files", files=files, data={"document_id": "doc-123"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["document_id"] == "doc-123"
    assert payload["results"][0]["kb_version"] == "draft"


def test_publish_document_endpoint(monkeypatch) -> None:
    class StubIngestService:
        async def publish_document(self, document_id: str) -> PublishResponse:
            assert document_id == "doc-123"
            return PublishResponse(document_id=document_id, chunks_published=3)

    def _stub_factory() -> StubIngestService:
        return StubIngestService()

    monkeypatch.setattr(ingest_route, "get_ingest_service", _stub_factory)
    client = TestClient(app)
    response = client.post("/api/ingest/documents/doc-123/publish")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == "doc-123"
    assert payload["chunks_published"] == 3
    assert payload["kb_version"] == "publish"


def test_list_documents_endpoint(monkeypatch) -> None:
    class StubIngestService:
        async def list_documents(self, kb_version=None):  # type: ignore[no-untyped-def]
            assert kb_version == "draft"
            return DocumentListResponse(
                items=[
                    DocumentSummary(
                        document_id="doc-123",
                        source="demo.md",
                        kb_version="draft",
                        chunks=2,
                        updated_at="2026-03-02T10:00:00+00:00",
                    )
                ]
            )

    def _stub_factory() -> StubIngestService:
        return StubIngestService()

    monkeypatch.setattr(ingest_route, "get_ingest_service", _stub_factory)
    client = TestClient(app)
    response = client.get("/api/ingest/documents?kb_version=draft")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["document_id"] == "doc-123"


def test_get_document_detail_endpoint(monkeypatch) -> None:
    class StubIngestService:
        async def get_document_detail(self, document_id: str, kb_version: str) -> DocumentDetailResponse:
            assert document_id == "doc-123"
            assert kb_version == "publish"
            return DocumentDetailResponse(
                document_id=document_id,
                kb_version=kb_version,
                chunks=[
                    DocumentChunkPreview(
                        chunk_id="chunk-1",
                        chunk_index=0,
                        total_chunks=1,
                        source="demo.md",
                        kb_version=kb_version,
                        doc_hash="hash",
                        text="hello",
                        ingested_at="2026-03-02T10:00:00+00:00",
                    )
                ],
            )

    def _stub_factory() -> StubIngestService:
        return StubIngestService()

    monkeypatch.setattr(ingest_route, "get_ingest_service", _stub_factory)
    client = TestClient(app)
    response = client.get("/api/ingest/documents/doc-123?kb_version=publish")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == "doc-123"
    assert payload["kb_version"] == "publish"
    assert payload["chunks"][0]["chunk_id"] == "chunk-1"


def test_delete_document_endpoint(monkeypatch) -> None:
    class StubIngestService:
        async def delete_document(self, document_id: str, kb_version: str) -> DeleteDocumentResponse:
            assert document_id == "doc-123"
            assert kb_version == "all"
            return DeleteDocumentResponse(
                document_id=document_id,
                kb_version=kb_version,
                weaviate_deleted=5,
                mongo_deleted=5,
            )

    def _stub_factory() -> StubIngestService:
        return StubIngestService()

    monkeypatch.setattr(ingest_route, "get_ingest_service", _stub_factory)
    client = TestClient(app)
    response = client.delete("/api/ingest/documents/doc-123?kb_version=all")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == "doc-123"
    assert payload["kb_version"] == "all"
    assert payload["weaviate_deleted"] == 5
    assert payload["mongo_deleted"] == 5


def test_clear_knowledge_base_endpoint(monkeypatch) -> None:
    class StubIngestService:
        async def clear_knowledge_base(self) -> ClearKnowledgeBaseResponse:
            return ClearKnowledgeBaseResponse(
                scope="all",
                weaviate_deleted=12,
                mongo_deleted=12,
            )

    def _stub_factory() -> StubIngestService:
        return StubIngestService()

    monkeypatch.setattr(ingest_route, "get_ingest_service", _stub_factory)
    client = TestClient(app)
    response = client.delete("/api/ingest/documents?confirm_text=CLEAR%20ALL")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "all"
    assert payload["weaviate_deleted"] == 12
    assert payload["mongo_deleted"] == 12


def test_clear_knowledge_base_requires_confirm_text() -> None:
    client = TestClient(app)
    response = client.delete("/api/ingest/documents?confirm_text=WRONG")
    assert response.status_code == 400
    assert "Invalid confirm_text" in response.json()["detail"]
