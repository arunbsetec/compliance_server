from pathlib import Path

import pymupdf


class UnreadableDocument(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NoReadableText(Exception):
    def __init__(self, message: str = "No readable text found in the document") -> None:
        self.message = message
        super().__init__(message)


def extract_pages(path: Path | str, content_type: str) -> list[dict]:
    path = Path(path)
    if content_type == "text/plain":
        return _pages_from_text(path)
    if content_type == "application/pdf":
        return _pages_from_pdf(path)
    raise UnreadableDocument("The file could not be read")


def _pages_from_text(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise NoReadableText
    return [{"page": 1, "text": text}]


def _pages_from_pdf(path: Path) -> list[dict]:
    try:
        pdf = pymupdf.open(path)
    except Exception as exc:
        raise UnreadableDocument("The file could not be read") from exc
    pages: list[dict] = []
    try:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page": index, "text": text})
    finally:
        pdf.close()
    if not pages:
        raise NoReadableText
    return pages
