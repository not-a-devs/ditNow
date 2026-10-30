"""DEMO mobile student card and fictional numeric-code attendance sandbox (FR-ATT-003/004).

PROCESS_MEMORY only: resets on restart, is not MariaDB persistence, not a real attendance ledger
and not production authorization.
"""

from app.features.demo_attendance.router import STATE_ATTR, get_actor, get_store, router
from app.features.demo_attendance.schemas import DEMO_CODE
from app.features.demo_attendance.store import (
    MAX_OWNERS,
    DemoAttendanceFull,
    DemoAttendanceStore,
)

__all__ = [
    "DEMO_CODE",
    "MAX_OWNERS",
    "STATE_ATTR",
    "DemoAttendanceFull",
    "DemoAttendanceStore",
    "get_actor",
    "get_store",
    "router",
]
