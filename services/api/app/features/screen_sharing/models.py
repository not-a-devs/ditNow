import re
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.common import ApiModel


class SessionRecord(ApiModel):
    id: UUID
    offering_id: UUID
    presenter_id: UUID  # Private common user UUID; never included in a public view.
    state: Literal["READY", "LIVE", "ENDED"] = "READY"
    revision: int = Field(ge=1)
    created_at: AwareDatetime
    expires_at: AwareDatetime


class Member(ApiModel):
    peer_id: UUID
    user_id: UUID  # Private common UUID, not a client-provided peer identity.
    generation: int = Field(ge=1)
    status: Literal["ACTIVE", "LEFT", "REVOKED"] = "ACTIVE"


class PeerView(ApiModel):
    peer_id: UUID
    generation: int = Field(ge=1)


class SessionView(ApiModel):
    id: UUID
    offering_id: UUID
    state: Literal["READY", "LIVE", "ENDED"]
    revision: int
    expires_at: AwareDatetime
    is_presenter: bool
    me: PeerView | None = None
    presenter: PeerView | None = None
    viewers: list[PeerView] = Field(default_factory=list, max_length=50)
    audio: Literal[False] = False
    recording: Literal[False] = False
    media_provider: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"


class ContextView(ApiModel):
    offering_id: UUID
    role: Literal["teacher", "student"]
    session: SessionView | None
    source_kind: Literal["DEMO"] = "DEMO"


class RevisionInput(ApiModel):
    expected_revision: int = Field(ge=1, strict=True)


class ReconnectInput(ApiModel):
    expected_generation: int = Field(ge=1, strict=True)


class SignalInput(ApiModel):
    target_peer_id: UUID
    generation: int = Field(ge=1, strict=True)
    target_generation: int = Field(ge=1, strict=True)
    kind: Literal["OFFER", "ANSWER", "ICE"]
    payload: str = Field(min_length=1, max_length=65536)

    @model_validator(mode="after")
    def bounded_video_only(self) -> "SignalInput":
        maximum = 2048 if self.kind == "ICE" else 65536
        if len(self.payload.encode("utf-8")) > maximum or "\x00" in self.payload:
            raise ValueError("Signal exceeds the allowed envelope")
        if self.kind == "ICE":
            if (
                not self.payload.startswith("candidate:")
                or "\n" in self.payload
                or "\r" in self.payload
            ):
                raise ValueError("An ICE candidate string is required")
        else:
            lines = self.payload.replace("\r\n", "\n").splitlines()
            media = [line for line in lines if line.startswith("m=")]
            directions = [
                line
                for line in lines
                if re.fullmatch(r"a=(sendonly|recvonly|sendrecv|inactive)", line)
            ]
            expected = "a=sendonly" if self.kind == "OFFER" else "a=recvonly"
            if (
                not lines
                or lines[0] != "v=0"
                or len(media) != 1
                or not media[0].startswith("m=video ")
                or not directions
                or any(direction not in {expected, "a=inactive"} for direction in directions)
            ):
                raise ValueError("Only a unidirectional video description is permitted")
        return self


class SignalRecord(ApiModel):
    sequence: int = Field(ge=1)
    sender_peer_id: UUID
    target_peer_id: UUID
    generation: int
    target_generation: int
    kind: Literal["OFFER", "ANSWER", "ICE"]
    payload: str


class SignalView(ApiModel):
    sequence: int
    sender_peer_id: UUID
    generation: int
    kind: Literal["OFFER", "ANSWER", "ICE"]
    payload: str


class SignalPage(ApiModel):
    items: list[SignalView] = Field(max_length=50)
    cursor: int = Field(ge=0)


class Claim(ApiModel):
    actor_id: UUID
    path: str
    key: str
    digest: str
    result_id: UUID
    result_generation: int | None = None
    sequence: int | None = None
