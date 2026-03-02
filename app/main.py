from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="RAG knowledge base chatbot service",
    )

    fastapi_app.include_router(api_router)
    fastapi_app.mount("/web", StaticFiles(directory="app/web"), name="web")

    @fastapi_app.get("/", tags=["root"])
    def root() -> FileResponse:
        return FileResponse("app/web/index.html")

    return fastapi_app


app = create_app()
