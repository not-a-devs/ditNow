"""현재 위치 → 건물 도보 예상 시간. LLM이 아니라 코드가 계산한다."""

import math

from .schemas import Building, UserLocation

EARTH_RADIUS_M = 6_371_000
# shortcut: 직선 거리 × 우회 보정으로 추정한다(캠퍼스 길·계단·출입구 미반영),
# 실제 경로가 필요하면 출입구 좌표와 보행 경로 그래프로 바꾼다
DETOUR_FACTOR = 1.3
WALK_M_PER_MIN = 75  # 4.5km/h, 평지 보통 걸음


def walk_estimate(user: UserLocation, building: Building) -> tuple[int, int] | None:
    """(경로 추정 거리 m, 도보 분). 건물 좌표가 없으면 None."""
    if building.lat is None or building.lng is None:
        return None
    lat1, lat2 = math.radians(user.lat), math.radians(building.lat)
    dlat = lat2 - lat1
    dlng = math.radians(building.lng - user.lng)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    straight = 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
    meters = round(straight * DETOUR_FACTOR)
    return meters, max(1, math.ceil(meters / WALK_M_PER_MIN))
