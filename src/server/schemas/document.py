from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

DocumentStatus = Literal["pending", "processing", "completed", "failed"]


class DocumentUploadResponse(BaseModel):
    id: UUID
    original_filename: str
    status: DocumentStatus
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: UUID
    original_filename: str
    uploaded_at: datetime
    status: DocumentStatus
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ExtractionFieldResponse(BaseModel):
    field_name: str
    value: str | None = None
    confidence: int = 0
    page_number: int | None = None
    source_excerpt: str | None = None


class DocumentDetail(BaseModel):
    id: UUID
    original_filename: str
    content_type: str
    file_size: int
    status: DocumentStatus
    error_message: str | None
    omitted_pages: list[int] = Field(default_factory=list)
    uploaded_at: datetime
    processed_at: datetime | None
    fields: list[ExtractionFieldResponse]


class StatusMessage(BaseModel):
    id: UUID
    status: DocumentStatus
    error_message: str | None = None
