import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID | None
    original_filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    processing_error: str | None
    extracted_char_count: int | None
    created_at: datetime
    processed_at: datetime | None


class DocumentDetailResponse(DocumentResponse):
    # Full extracted text is only included on the single-document GET, not in
    # list responses — a list of documents shouldn't ship every document's
    # entire body over the wire just to render a table.
    extracted_text: str | None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
