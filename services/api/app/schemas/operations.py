"""Request coordination value objects; no replay cache or database locking implementation."""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import ApiModel


class RevisionPrecondition(ApiModel):
    expected_revision: int = Field(ge=1)


class IdempotencyScope(ApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    actor_id: UUID
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    canonical_path: str = Field(min_length=1, max_length=2048)
    key: str = Field(min_length=1, max_length=128, pattern=r"^[!-~]+$")
    body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def canonical_target(self):
        if (
            not self.canonical_path.startswith("/api/v1/")
            or "?" in self.canonical_path
            or "#" in self.canonical_path
            or "%" in self.canonical_path
            or "//" in self.canonical_path
            or any(segment in {".", ".."} for segment in self.canonical_path.split("/"))
            or not self.canonical_path.isascii()
            or any(c.isspace() for c in self.canonical_path)
        ):
            raise ValueError("canonical target must be a normalized versioned resource path")
        return self

    @property
    def namespace(self) -> tuple[UUID, str, str, str]:
        return (self.actor_id, self.method, self.canonical_path, self.key)
