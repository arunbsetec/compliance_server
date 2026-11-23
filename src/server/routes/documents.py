import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.orm import Session

from server.core.config import settings
from server.core.deps import get_current_user, user_from_access_token
from server.core.ws import connection_manager
from server.db.session import SessionLocal, get_db
from server.models.document import COMPLETED, FAILED, Document
from server.models.user import User
from server.schemas.document import DocumentDetail, DocumentListItem, DocumentUploadResponse, StatusMessage
from server.services import document_service
from server.services.extraction_service import process_document

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


async def run_extraction(document_id: uuid.UUID) -> None:
    await asyncio.to_thread(process_document, document_id)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> Document:
    data = await _read_limited(file)
    try:
        document = document_service.save_upload(
            db,
            current_user,
            file.filename or "",
            file.content_type or "",
            data,
        )
    except document_service.UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    background_tasks.add_task(run_extraction, document.id)
    return document


@router.get("/documents", response_model=list[DocumentListItem])
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    return document_service.list_documents(db, current_user)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentDetail:
    document = document_service.get_document(db, current_user, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/retry/{document_id}", response_model=DocumentUploadResponse)
def retry_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    try:
        document = document_service.retry_document(db, current_user, document_id)
    except document_service.RetryNotAllowed:
        raise HTTPException(status_code=409, detail="Only a failed document can be retried")
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    background_tasks.add_task(run_extraction, document.id)
    return document


@router.websocket("/documents/{document_id}/status")
async def document_status(
    websocket: WebSocket,
    document_id: uuid.UUID,
    token: Annotated[str, Query()],
) -> None:
    await websocket.accept()
    db = SessionLocal()
    try:
        user = user_from_access_token(db, token)
        document = db.get(Document, document_id) if user is not None else None
        if user is None or document is None or document.user_id != user.id:
            await websocket.close(code=1008)
            return
    finally:
        db.close()

    await connection_manager.connect(document_id, websocket)
    try:
        db = SessionLocal()
        try:
            document = db.get(Document, document_id)
            if document is None or document.user_id != user.id:
                await websocket.close(code=1008)
                return
            message = StatusMessage(
                id=document.id,
                status=document.status,
                error_message=document.error_message,
            )
            terminal = document.status in {COMPLETED, FAILED}
        finally:
            db.close()

        logger.info(
            "status socket connected document_id=%s status=%s",
            message.id,
            message.status,
        )
        await websocket.send_json(message.model_dump(mode="json"))
        if terminal:
            await websocket.close()
            return
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
    finally:
        connection_manager.disconnect(document_id, websocket)


async def _read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit")
        chunks.append(chunk)
    return b"".join(chunks)
