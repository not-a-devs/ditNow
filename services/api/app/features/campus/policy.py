"""Pure authorization rules for RBAC-DEPT and RBAC-NOT. No I/O; callers fetch records first."""

from collections.abc import Iterable

from app.features.campus.domain import (
    Audience,
    AudienceType,
    CampusActor,
    Channel,
    ChannelKind,
    DeliveryTarget,
    Notice,
    NoticeStatus,
)


def can_access_channel(actor: CampusActor, channel: Channel) -> bool:
    for membership in actor.memberships:
        if membership.department_id != channel.department_id:
            continue
        if channel.kind is ChannelKind.DEPARTMENT_ALL:
            return True
        # Grade channels require an exact current grade; a department-only membership
        # (e.g. staff without grade) is denied until a policy grants wider access.
        if membership.grade is not None and membership.grade == channel.grade:
            return True
    return False


def belongs_to_department(actor: CampusActor, department_id: object) -> bool:
    return any(m.department_id == department_id for m in actor.memberships)


def visible_channels(actor: CampusActor, channels: Iterable[Channel]) -> list[Channel]:
    return [channel for channel in channels if can_access_channel(actor, channel)]


def can_author(actor: CampusActor, audience: Audience) -> bool:
    # Exact scope match only. Department scope does not silently imply grade scopes.
    return audience in actor.notice_author_scopes


def is_in_audience(actor: CampusActor, audience: Audience) -> bool:
    if audience.type is AudienceType.SCHOOL:
        return bool(actor.memberships)
    if audience.type is AudienceType.DEPARTMENT:
        return belongs_to_department(actor, audience.department_id)
    return any(
        m.department_id == audience.department_id and m.grade == audience.grade
        for m in actor.memberships
    )


def actor_audiences(actor: CampusActor) -> list[Audience]:
    """Audiences whose published notices this actor may list."""
    if not actor.memberships:
        return []
    audiences: dict[Audience, None] = {Audience(AudienceType.SCHOOL): None}
    for m in actor.memberships:
        audiences[Audience(AudienceType.DEPARTMENT, m.department_id)] = None
        if m.grade is not None:
            audiences[Audience(AudienceType.DEPARTMENT_GRADE, m.department_id, m.grade)] = None
    return list(audiences)


def can_read_notice(actor: CampusActor, notice: Notice) -> bool:
    if can_author(actor, notice.audience):
        return True
    if notice.status is NoticeStatus.DRAFT:
        return False
    return is_in_audience(actor, notice.audience)


def delivery_targets(audience: Audience) -> list[DeliveryTarget]:
    """DFLT-004: school-wide notices go to feed/notifications, never copied into every chat."""
    if audience.type is AudienceType.SCHOOL:
        return []
    assert audience.department_id is not None
    if audience.type is AudienceType.DEPARTMENT:
        return [DeliveryTarget(audience.department_id, None)]
    return [DeliveryTarget(audience.department_id, audience.grade)]
