"""Compose existing read-only public services, without copying their source records."""

import re
import unicodedata
from urllib.parse import quote, urlencode

from app.core.errors import ApiError
from app.features.discovery.models import (
    DiscoveryItem,
    DiscoveryPage,
    FacilitySource,
    GuideSource,
    Kind,
)
from app.features.public_campus.service import (
    PublicCampusService,
    get_public_campus_service,
    normalize,
)
from app.integrations.chatbot.campus import CampusSearch, get_campus_search
from app.schemas.common import ErrorCode

FACILITY_CANDIDATE_LIMIT = 100
_SOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class DiscoveryService:
    def __init__(self, guides: PublicCampusService, facilities: CampusSearch):
        self.guides, self.facilities = guides, facilities

    def search(self, query: str, kind: Kind, offset: int, limit: int) -> DiscoveryPage:
        query = normalize(query)
        if (
            not query
            or len(query) > 200
            or not any(character.isalnum() for character in query)
            or any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in query)
            or kind not in {"all", "guide", "facility"}
            or not 0 <= offset <= 200
            or not 1 <= limit <= 20
        ):
            raise ApiError(ErrorCode.VALIDATION)
        items = []
        complete = True
        if kind != "facility":
            # PublicSnapshot has at most100 records; its existing page contract allows50.
            first = self.guides.list_guides(query, None, None, 0, 50)
            pages = [first]
            if first.total > 50:
                pages.append(self.guides.list_guides(query, None, None, 50, 50))
            for page in pages:
                for record in page.items:
                    items.append(
                        DiscoveryItem(
                            id=f"guide:{record.id}",
                            kind="guide",
                            title=record.title,
                            summary=record.summary,
                            detail_path="/app/information?" + urlencode({"guide": record.id}),
                            source=GuideSource(
                                evidence=record.source, snapshot_version=page.snapshot_version
                            ),
                        )
                    )
        if kind != "guide":
            # One extra candidate distinguishes a full result from the bounded collection.
            result = self.facilities.search(query, FACILITY_CANDIDATE_LIMIT + 1)
            complete = len(result.hits) <= FACILITY_CANDIDATE_LIMIT
            seen = set()
            for hit in result.hits[:FACILITY_CANDIDATE_LIMIT]:
                if not _SOURCE_ID.fullmatch(hit.source_id) or hit.source_id in seen:
                    complete = False
                    continue
                seen.add(hit.source_id)
                items.append(
                    DiscoveryItem(
                        id=f"facility:{hit.source_id}",
                        kind="facility",
                        title=hit.name[:160],
                        summary=hit.text[:700],
                        detail_path="/app/ai?q=" + quote(hit.name, safe=""),
                        source=FacilitySource(),
                    )
                )
        # Same bounded source snapshots yield deterministic global pages, independent of score ties.
        items.sort(key=lambda item: (item.kind, item.id))
        return DiscoveryPage(
            query=query,
            kind=kind,
            items=items[offset : offset + limit],
            total=len(items),
            counts={key: sum(item.kind == key for item in items) for key in ("guide", "facility")},
            offset=offset,
            limit=limit,
            complete=complete,
        )


def get_discovery_service() -> DiscoveryService:
    try:
        return DiscoveryService(get_public_campus_service(), get_campus_search())
    except (OSError, ValueError):
        raise ApiError(ErrorCode.UNAVAILABLE) from None
