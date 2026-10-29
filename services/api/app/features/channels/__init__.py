"""TASK-U: student free channels + official-channel request submission (first pass).

Not mounted by this package. ``router`` fails closed with 503 until root overrides
``get_channels_actor`` (verified auth bridge) and ``get_channels_service`` (approved MariaDB unit
of work). No approval, official badge or staff-claim capability exists here.
"""

from app.features.channels.router import get_channels_actor, get_channels_service, router

__all__ = ["get_channels_actor", "get_channels_service", "router"]
