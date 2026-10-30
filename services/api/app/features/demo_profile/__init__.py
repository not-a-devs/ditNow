"""DEMO / PROCESS_MEMORY activity-preference sandbox for FR-AUTH-003 (partial).

Not a profile or identity record: the canonical identity stays with the shared auth owner and
``app.features.profiles`` stays dormant. ``router`` fails closed (503) until the root owner
overrides ``get_actor`` and sets ``app.state.demo_profile``. Data resets on process restart.
"""

from app.features.demo_profile.router import PATH, get_actor, get_store, router
from app.features.demo_profile.schemas import (
    DemoInterest,
    DemoProfilePreferences,
    DemoProfileUpdate,
    SkillLevel,
)
from app.features.demo_profile.store import MAX_OWNERS, DemoProfileStore

__all__ = [
    "MAX_OWNERS",
    "PATH",
    "DemoInterest",
    "DemoProfilePreferences",
    "DemoProfileStore",
    "DemoProfileUpdate",
    "SkillLevel",
    "get_actor",
    "get_store",
    "router",
]
