import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from server.core.config import settings
from server.core.ws import connection_manager
from server.models.document import FAILED, FIELD_NAMES, PENDING, Document, ExtractionField
from server.models.user import User
from server.schemas.document import DocumentDetail, ExtractionFieldResponse

ALLOWED_FILES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


class UploadRejected(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class RetryNotAllowed(Exception):
    pass


def save_upload(db: Session, user: User, filename: str, content_type: str, data: bytes) -> Document:
    suffix, media_type = _validated_file(filename, content_type, data)
    document_id = uuid.uuid4()
    directory = settings.resolved_upload_dir() / str(user.id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document_id}{suffix}"
    path.write_bytes(data)
    document = Document(
        id=document_id,
        user_id=user.id,
        original_filename=_safe_filename(filename),
        storage_path=str(path),
        content_type=media_type,
        file_size=len(data),
        status=PENDING,
        omitted_pages=[],
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, user: User) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.uploaded_at.desc())
        )
    )


def get_document(db: Session, user: User, document_id: uuid.UUID) -> DocumentDetail | None:
    document = _owned_document(db, user, document_id)
    if document is None:
        return None
    return _detail(db, document)


def retry_document(db: Session, user: User, document_id: uuid.UUID) -> Document | None:
    document = _owned_document(db, user, document_id)
    if document is None:
        return None
    if document.status != FAILED:
        raise RetryNotAllowed
    db.execute(delete(ExtractionField).where(ExtractionField.document_id == document.id))
    document.status = PENDING
    document.error_message = None
    document.omitted_pages = []
    document.processed_at = None
    db.commit()
    db.refresh(document)
    connection_manager.publish(
        document.id,
        {"id": str(document.id), "status": document.status, "error_message": None},
    )
    return document


def _owned_document(db: Session, user: User, document_id: uuid.UUID) -> Document | None:
    return db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )


def _detail(db: Session, document: Document) -> DocumentDetail:
    stored = {
        field.field_name: field
        for field in db.scalars(
            select(ExtractionField).where(ExtractionField.document_id == document.id)
        )
    }
    fields = []
    for name in FIELD_NAMES:
        field = stored.get(name)
        if field is None:
            fields.append(ExtractionFieldResponse(field_name=name))
            continue
        fields.append(
            ExtractionFieldResponse(
                field_name=field.field_name,
                value=field.value,
                confidence=field.confidence,
                page_number=field.page_number,
                source_excerpt=field.source_excerpt,
            )
        )
    omitted = document.omitted_pages or []
    return DocumentDetail(
        id=document.id,
        original_filename=document.original_filename,
        content_type=document.content_type,
        file_size=document.file_size,
        status=document.status,
        error_message=document.error_message,
        omitted_pages=list(omitted),
        uploaded_at=document.uploaded_at,
        processed_at=document.processed_at,
        fields=fields,
    )


def _validated_file(filename: str, content_type: str, data: bytes) -> tuple[str, str]:
    if len(data) > settings.max_upload_bytes:
        raise UploadRejected(413, "File exceeds the 10 MB limit")
    if not data:
        raise UploadRejected(400, "File is empty")
    suffix = Path(filename or "").suffix.lower()
    expected = ALLOWED_FILES.get(suffix)
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if expected is None or media_type != expected:
        raise UploadRejected(400, "Only PDF and TXT files are allowed")
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        raise UploadRejected(400, "File is not a readable PDF")
    if suffix == ".txt" and not data.decode("utf-8", errors="replace").strip():
        raise UploadRejected(400, "File is empty")
    return suffix, expected


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload").name.strip() or "upload"
    return name[:255]
