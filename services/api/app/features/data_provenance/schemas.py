"""Read-only DTOs for the FR-ADM-004 provenance explanation (no administration workflow)."""

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel

ProvenanceLabel = Literal["DEMO", "OFFICIAL_PUBLIC", "PLATFORM", "UNKNOWN"]
PROVENANCE_LABELS: tuple[ProvenanceLabel, ...] = ("DEMO", "OFFICIAL_PUBLIC", "PLATFORM", "UNKNOWN")


class ProvenanceLabelInfo(ApiModel):
    label: ProvenanceLabel
    title: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=300)
    user_guidance: str = Field(min_length=1, max_length=300)


class ProvenanceStatus(ApiModel):
    """Fixed facts about this platform; every value is a constant, never configuration."""

    school_sso_connected: Literal[False] = False
    financial_effect: Literal["NONE"] = "NONE"
    persistence: Literal["IN_PROCESS_FIXED"] = "IN_PROCESS_FIXED"
    content_administration: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"


class ProvenanceOverview(ApiModel):
    catalog_version: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=60)
    feature_ids: list[str]
    notice: str = Field(min_length=1, max_length=400)
    status: ProvenanceStatus
    labels: list[ProvenanceLabelInfo] = Field(min_length=4, max_length=4)
