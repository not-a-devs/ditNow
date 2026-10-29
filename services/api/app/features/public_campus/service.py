import unicodedata
from functools import lru_cache
from pathlib import Path

from app.core.errors import ApiError
from app.features.public_campus.models import (
    Category,
    PublicGuide,
    PublicGuideCard,
    PublicGuidePage,
    PublicSnapshot,
    Site,
)
from app.schemas.common import ErrorCode


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class PublicCampusService:
    def __init__(self, snapshot: PublicSnapshot):
        self._snapshot = snapshot

    def list_guides(
        self, query: str, category: Category | None, site: Site | None, offset: int, limit: int
    ) -> PublicGuidePage:
        terms = normalize(query).split()
        matches = []
        for record in sorted(self._snapshot.records, key=lambda item: item.id):
            if category is not None and record.category != category:
                continue
            if site is not None and record.source.site != site:
                continue
            searchable = normalize(
                " ".join(
                    [
                        record.title,
                        record.summary,
                        *record.tags,
                        *(
                            paragraph
                            for section in record.sections
                            for paragraph in section.paragraphs
                        ),
                    ]
                )
            )
            if all(term in searchable for term in terms):
                matches.append(record)
        return PublicGuidePage(
            items=[
                PublicGuideCard(
                    **record.model_dump(exclude={"sections", "feature_ids", "content_kind"})
                )
                for record in matches[offset : offset + limit]
            ],
            total=len(matches),
            offset=offset,
            limit=limit,
            snapshot_version=self._snapshot.version,
        )

    def get_guide(self, record_id: str) -> PublicGuide:
        for record in self._snapshot.records:
            if record.id == record_id:
                return record.model_copy(deep=True)
        raise ApiError(ErrorCode.NOT_FOUND)


@lru_cache(maxsize=1)
def get_public_campus_service() -> PublicCampusService:
    try:
        source = Path(__file__).with_name("snapshot.json").read_text(encoding="utf-8")
        return PublicCampusService(PublicSnapshot.model_validate_json(source))
    except (OSError, ValueError):
        raise ApiError(ErrorCode.UNAVAILABLE) from None
