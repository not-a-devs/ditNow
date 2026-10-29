"""Reuse DEC-020 token authority with caller-owned, approved connection configuration."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from chatbot.app.auth import resolve_token
from chatbot.app.models import StudentRow
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ExistingLegacyTokenVerifier:
    """Read only; opens a NEW session per check so ORM identity maps cannot cache revocation.

    The injected factory must provide a new session on the approved TLS engine, never a scoped
    reused session or a separately seeded database. This adapter does not build engines, load
    environment files, create tables, authenticate passwords, issue tokens, commit, or log.
    """

    def __init__(self, sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]]):
        self._sessions = sessions

    async def verify(self, token: SecretStr) -> str | None:
        async with self._sessions() as db:
            subject = await resolve_token(db, token.get_secret_value())
            if subject is None:
                return None
            # Avoid loading names/password hashes or assuming all legacy students are DEMO.
            existing = await db.scalar(
                select(StudentRow.student_id).where(StudentRow.student_id == subject)
            )
            return subject if existing == subject else None
