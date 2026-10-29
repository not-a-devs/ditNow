from app.features.campus_travel.models import TravelInput, TravelResult


def calculate_travel(value: TravelInput) -> TravelResult:
    """Pure calculation: no persistence, route estimation or institutional policy."""
    gap = int((value.next_starts_at - value.previous_ends_at).total_seconds())
    travel = value.estimated_travel_minutes * 60
    remaining = gap - travel
    status = (
        "OVERLAP"
        if gap < 0
        else "INSUFFICIENT"
        if remaining < 0
        else "NO_MARGIN"
        if remaining == 0
        else "HAS_MARGIN"
    )
    return TravelResult(
        previous_ends_at=value.previous_ends_at,
        next_starts_at=value.next_starts_at,
        gap_seconds=gap,
        travel_seconds=travel,
        remaining_seconds=remaining,
        status=status,
    )
