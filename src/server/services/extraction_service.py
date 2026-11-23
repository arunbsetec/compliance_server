import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

from server.core.config import settings
from server.core.ws import connection_manager
from server.db.session import SessionLocal
from server.models.document import FAILED, FIELD_NAMES, PROCESSING, COMPLETED, Document, ExtractionField
from server.services.groq_client import GroqNotConfigured, GroqRequestFailed, extract_fields
from server.services.text_extract import NoReadableText, UnreadableDocument, extract_pages

logger = logging.getLogger(__name__)


class ExtractionFailed(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def process_document(document_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.status = PROCESSING
        document.error_message = None
        db.commit()
        _publish(document)

        try:
            fields, omitted_pages = _extract(document)
        except ExtractionFailed as exc:
            _mark_failed(db, document, exc.message)
            return
        except Exception:
            logger.exception("extraction failed document_id=%s", document_id)
            _mark_failed(db, document, "Extraction failed")
            return

        db.execute(delete(ExtractionField).where(ExtractionField.document_id == document.id))
        for field in fields:
            db.add(ExtractionField(document_id=document.id, **field))
        document.status = COMPLETED
        document.error_message = None
        document.omitted_pages = omitted_pages
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        _publish(document, close=True)
    finally:
        db.close()


def _extract(document: Document) -> tuple[list[dict], list[int]]:
    try:
        pages = extract_pages(document.storage_path, document.content_type)
    except (UnreadableDocument, NoReadableText) as exc:
        raise ExtractionFailed(exc.message) from exc
    except OSError as exc:
        raise ExtractionFailed("The file could not be read") from exc

    selected, omitted_pages = _pages_that_fit(pages)
    document_text = "\n".join(selected)
    try:
        fields = extract_fields(document_text)
    except (GroqNotConfigured, GroqRequestFailed) as exc:
        raise ExtractionFailed(exc.message) from exc
    if len(fields) != len(FIELD_NAMES):
        raise ExtractionFailed("The extraction response could not be read")
    return fields, omitted_pages


def _pages_that_fit(pages: list[dict]) -> tuple[list[str], list[int]]:
    selected: list[str] = []
    used = 0
    budget = settings.max_document_characters
    for index, page in enumerate(pages):
        block = f"[Page {page['page']}]\n{page['text']}\n"
        if used + len(block) <= budget:
            selected.append(block)
            used += len(block)
            continue
        if index == 0:
            raise ExtractionFailed("document too long")
        return selected, [item["page"] for item in pages[index:]]
    return selected, []


def _mark_failed(db, document: Document, message: str) -> None:
    document.status = FAILED
    document.error_message = message
    document.processed_at = datetime.now(timezone.utc)
    db.commit()
    logging.getLogger("uvicorn.error").info(
        "document failed document_id=%s reason=%s",
        document.id,
        message,
    )
    _publish(document, close=True)


def _publish(document: Document, close: bool = False) -> None:
    try:
        connection_manager.publish(
            document.id,
            {
                "id": str(document.id),
                "status": document.status,
                "error_message": document.error_message,
            },
            close=close,
        )
    except Exception:
        logger.exception("status publish failed document_id=%s", document.id)
