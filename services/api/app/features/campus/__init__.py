"""TASK-CAMPUS: department/grade chat, official notices, academic calendar (first pass).

Not mounted by this package. Root integration includes ``router`` (fail-closed 503) or a
router built with an injected ``CampusRuntime``.
"""

from app.features.campus.router import CampusRuntime, build_campus_router, router

__all__ = ["CampusRuntime", "build_campus_router", "router"]
