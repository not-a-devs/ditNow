from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.schemas.common import ApiModel


class LibraryActor(ApiModel):
    user_id: UUID


class LibraryPolicy(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    source_kind: Literal["DEMO"] = "DEMO"
    renewal_days: int = Field(ge=1, le=90)
    max_renewals: int = Field(ge=0, le=10)
    allow_overdue_renewal: bool
    renewal_base: Literal["due_at", "request_time"]
    max_active_bookings: int = Field(ge=1, le=10)


class MemberGrant(ApiModel):
    active: bool
    eligible: bool


class CatalogTitle(ApiModel):
    id: UUID
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=100)
    available_copies: int = Field(ge=0)
    public_reference_url: str | None = None
    source_kind: Literal["DEMO"] = "DEMO"

    @field_validator("public_reference_url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not value.isascii()
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Public HTTPS reference required")
        try:
            _ = parsed.port
        except ValueError:
            raise ValueError("Invalid reference port") from None
        return value


class CatalogPage(ApiModel):
    items: list[CatalogTitle]
    offset: int
    has_more: bool
    source_kind: Literal["DEMO"] = "DEMO"


class LoanView(ApiModel):
    id: UUID
    title: str
    due_at: AwareDatetime
    state: Literal["active", "returned"]
    renewal_count: int = Field(ge=0)
    renewable: bool
    revision: int = Field(ge=1)
    source_kind: Literal["DEMO"] = "DEMO"

    @field_validator("due_at")
    @classmethod
    def utc_due(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class LoanRecord(LoanView):
    owner_id: UUID


class WishInput(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=100)
    reason: str = Field(max_length=500)

    @field_validator("title", "author")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip()


class WishView(WishInput):
    id: UUID
    state: Literal["requested", "reviewing", "completed", "cancelled"]
    created_at: AwareDatetime
    source_kind: Literal["DEMO"] = "DEMO"


class WishRecord(WishView):
    owner_id: UUID


class Slot(ApiModel):
    id: UUID
    space_id: UUID
    space_name: str = Field(min_length=1, max_length=100)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    available: bool
    revision: int = Field(ge=1)
    source_kind: Literal["DEMO"] = "DEMO"

    @model_validator(mode="after")
    def ordered(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Slot end must follow start")
        return self


class BookingView(ApiModel):
    id: UUID
    slot_id: UUID
    space_name: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    state: Literal["reserved", "cancelled"]
    revision: int = Field(ge=1)
    source_kind: Literal["DEMO"] = "DEMO"


class BookingRecord(BookingView):
    owner_id: UUID


class RevisionInput(ApiModel):
    expected_revision: int = Field(ge=1)


class LibraryOverview(ApiModel):
    loans: list[LoanView]
    wishes: list[WishView]
    bookings: list[BookingView]
    policy: LibraryPolicy
    source_kind: Literal["DEMO"] = "DEMO"
