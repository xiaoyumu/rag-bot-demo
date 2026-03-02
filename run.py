import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    log_level = str(settings.log_level).lower()
    is_dev = str(settings.app_env).lower() == "dev"
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=log_level,
        reload=is_dev,
    )


if __name__ == "__main__":
    main()
