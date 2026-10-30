"""Bind the fictional process-memory demo routers to the existing common login context.

Called by the app factory only under ``settings.p0_runtime_enabled``. No new identity, role,
grant, DB row or network call is created here: each module's actor placeholder is overridden with
the current approved binding resolved by the canonical ``get_context`` on every request. Stores
are owned by the application instance (``app.state``), never module globals; a restart or a
second worker starts with empty fictional data (not MariaDB persistence).
"""

from importlib import import_module
from types import ModuleType
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI

from app.features.demo_services.models import DemoActor
from app.integrations.platform_runtime.dependencies import Context

API_PREFIX = "/api/v1"


async def demo_owner(ctx: Context) -> UUID:
    """Current verified common identity; never read from headers, body, query or old sessions."""
    return ctx.binding.principal.user_id


async def demo_services_actor(owner: Annotated[UUID, Depends(demo_owner)]) -> DemoActor:
    return DemoActor(user_id=owner)


DEMO_ROUTER_MODULES = {
    "services": "app.features.demo_services.router",
    "attendance": "app.features.demo_attendance.router",
    "profile": "app.features.demo_profile.router",
    "action_center": "app.features.demo_action_center.router",
    "channels": "app.features.demo_channels.router",
}


def demo_router_modules() -> dict[str, ModuleType]:
    """Explicit router submodules. A package ``__init__`` re-exporting ``router`` would make
    ``from package import router`` yield the APIRouter object, not the module that owns the actor
    placeholder, so the hardcoded submodule paths are imported directly. Missing modules raise
    at startup; there is no silent fallback."""
    return {name: import_module(path) for name, path in DEMO_ROUTER_MODULES.items()}


def configure_demo_runtime(application: FastAPI) -> None:
    from app.features.demo_action_center.store import DemoActionCenterStore
    from app.features.demo_attendance.store import DemoAttendanceStore
    from app.features.demo_channels.store import DemoChannelsStore
    from app.features.demo_profile.store import DemoProfileStore
    from app.features.demo_services.service import DemoServices

    modules = demo_router_modules()
    services = modules["services"]
    attendance = modules["attendance"]
    profile = modules["profile"]
    action_center = modules["action_center"]
    channels = modules["channels"]

    application.state.demo_services = DemoServices()
    application.state.demo_attendance = DemoAttendanceStore()
    application.state.demo_profile = DemoProfileStore()
    application.state.demo_action_center = DemoActionCenterStore()
    application.state.demo_channels = DemoChannelsStore()

    application.dependency_overrides[services.get_demo_actor] = demo_services_actor
    for module in (attendance, profile, action_center, channels):
        application.dependency_overrides[module.get_actor] = demo_owner

    for module in (services, attendance, profile, action_center, channels):
        application.include_router(module.router, prefix=API_PREFIX)


__all__ = [
    "API_PREFIX",
    "DEMO_ROUTER_MODULES",
    "configure_demo_runtime",
    "demo_owner",
    "demo_router_modules",
    "demo_services_actor",
]
