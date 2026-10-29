import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.common import ApiModel


class Content(ApiModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or any(
            unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in {"\n", "\t"} for c in value
        ):
            raise ValueError("Text cannot be blank")
        return value.strip()


class QuestionInput(Content):
    title: str = Field(min_length=1, max_length=160)

    @field_validator("title")
    @classmethod
    def title_nonblank(cls, value: str) -> str:
        if not value.strip() or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
            raise ValueError("Title must be a nonblank single line")
        return value.strip()


class QuestionUpdate(QuestionInput):
    expected_revision: int = Field(ge=1)


class CommentUpdate(Content):
    expected_revision: int = Field(ge=1)


class Item(ApiModel):
    """Private adapter record: owner_id never belongs to a student-facing response."""

    id: UUID
    department_id: UUID
    owner_id: UUID
    kind: Literal["QUESTION", "COMMENT"]
    question_id: UUID | None = None
    title: str | None = None
    body: str
    status: Literal["ACTIVE", "DELETED"] = "ACTIVE"
    record_source: Literal["DEMO"]
    revision: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ItemView(ApiModel):
    id: UUID
    department_id: UUID
    kind: Literal["QUESTION", "COMMENT"]
    question_id: UUID | None
    title: str | None
    body: str
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    is_mine: bool
    record_source: Literal["DEMO"] = "DEMO"
    identity_display_policy: Literal["BLOCKED"] = "BLOCKED"


class AttachmentMetadata(ApiModel):
    id: UUID
    filename: str = Field(min_length=1, max_length=180)
    size_bytes: int = Field(ge=0, le=100_000_000)
    storage: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"

    @field_validator("filename")
    @classmethod
    def safe_name(cls, value: str) -> str:
        if not value.strip() or any(
            unicodedata.category(c) in {"Cc", "Cf", "Cs"} or c in "/\\:" for c in value
        ):
            raise ValueError("Only a display filename without paths is allowed")
        return value


class RevisionMetadata(ApiModel):
    revision: int = Field(ge=1)
    changed_at: AwareDatetime
    event: Literal["CREATED", "CONTENT_REVISED", "PUBLISHED", "ARCHIVED"]


class NoticeView(ApiModel):
    id: UUID
    title: str
    body: str
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
    revision: int
    updated_at: AwareDatetime
    attachments: list[AttachmentMetadata] = Field(max_length=100)
    history: list[RevisionMetadata] = Field(max_length=100)
    school_connection: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"


class NoticeSummary(ApiModel):
    id: UUID
    title: str
    status: Literal["PUBLISHED", "ARCHIVED"]
    revision: int


class Page[T](ApiModel):
    items: list[T]
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)


class Claim(ApiModel):
    actor_id: UUID
    path: str
    key: str
    digest: str
    item_id: UUID

    @property
    def namespace(self) -> tuple[UUID, str, str]:
        return self.actor_id, self.path, self.key
