from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


class UnsupportedFileTypeError(ValueError):
    pass


def load_text_from_bytes(filename: str, payload: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md"}:
        return payload.decode("utf-8", errors="ignore")
    if extension == ".pdf":
        reader = PdfReader(BytesIO(payload))
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    raise UnsupportedFileTypeError(f"Unsupported file type: {extension or '<none>'}")
