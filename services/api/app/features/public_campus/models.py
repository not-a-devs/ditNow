from datetime import date
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ApiModel

Category = Literal["university", "campus", "disclosure", "news", "department"]
Site = Literal["university", "cs"]
FeatureId = Literal[
    "FR-WEB-001", "FR-WEB-002", "FR-WEB-003", "FR-WEB-004", "FR-DEPT-007", "FR-DEPT-008"
]


class SourceEvidence(ApiModel):
    url: str
    site: Site
    checked_at: date
    existence: Literal["VERIFIED"] = "VERIFIED"
    processing_rules: Literal["PARTIAL"] = "PARTIAL"
    freshness: Literal["UNKNOWN"] = "UNKNOWN"
    evidence: str = Field(min_length=1, max_length=600)
    checked_scope: str = (
        "공식 페이지의 도구 반환본 확인. 원문 수정일이나 실시간 최신성을 보장하지 않음."
    )

    @field_validator("url")
    @classmethod
    def official_public_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        try:
            valid_port = parsed.port is None
        except ValueError:
            valid_port = False
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.dit.ac.kr"
            or not valid_port
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.path not in {"/kr/", "/kr/index.php", "/cs/", "/cs/index.php"}
            or any(key != "pCode" for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
            or not value.isascii()
            or any(character.isspace() for character in value)
        ):
            raise ValueError("An allowlisted official public page URL is required")
        return value

    @model_validator(mode="after")
    def site_matches_url(self) -> "SourceEvidence":
        expected = "/cs/" if self.site == "cs" else "/kr/"
        if not urlsplit(self.url).path.startswith(expected):
            raise ValueError("Source site and URL must match")
        return self


class GuideSection(ApiModel):
    heading: str = Field(min_length=1, max_length=120)
    paragraphs: list[str] = Field(min_length=1, max_length=6)

    @field_validator("paragraphs")
    @classmethod
    def bounded_paragraphs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 1200 for value in values):
            raise ValueError("Paragraphs must contain bounded plain text")
        return values


class PublicGuide(ApiModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    title: str = Field(min_length=1, max_length=160)
    category: Category
    feature_ids: list[FeatureId] = Field(min_length=1, max_length=6)
    summary: str = Field(min_length=1, max_length=700)
    sections: list[GuideSection] = Field(min_length=1, max_length=8)
    tags: list[str] = Field(max_length=12)
    source: SourceEvidence
    content_kind: Literal["EDITORIAL_PUBLIC_SUMMARY"] = "EDITORIAL_PUBLIC_SUMMARY"

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 50 for value in values):
            raise ValueError("Tags must contain bounded plain text")
        return values


class PublicGuideCard(ApiModel):
    id: str
    title: str
    category: Category
    summary: str
    tags: list[str]
    source: SourceEvidence


class PublicSnapshot(ApiModel):
    version: str = Field(pattern=r"^public-campus-\d{4}-\d{2}-\d{2}-v\d+$")
    captured_at: date
    records: list[PublicGuide] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def consistent_snapshot(self) -> "PublicSnapshot":
        if len({record.id for record in self.records}) != len(self.records):
            raise ValueError("Snapshot record IDs must be unique")
        if any(record.source.checked_at > self.captured_at for record in self.records):
            raise ValueError("Evidence cannot be checked after this snapshot")
        return self


class PublicGuidePage(ApiModel):
    items: list[PublicGuideCard]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)
    snapshot_version: str
    notice: str = (
        "공식 공개 페이지를 참고한 DIT NOW 편집 요약입니다. "
        "최신 공식 안내와 처리 규칙은 원문을 확인하세요."
    )
