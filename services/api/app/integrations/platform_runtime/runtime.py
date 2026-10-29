"""One strict engine, existing login/token authority and current approved canonical bindings."""

import asyncio
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from chatbot.app.auth import _token_hash, authenticate, issue_token, resolve_token
from chatbot.app.models import AuthSessionRow, StudentRow
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import VerifiedPrincipal
from app.core.errors import ApiError
from app.db.live_check import read_only_report
from app.db.p0_runtime import P0Executor, P0Services
from app.integrations.platform_runtime.bindings import BoundSession, bind_student
from app.schemas.auth import LoginData
from app.schemas.common import ErrorCode, utc_now

T = TypeVar("T")


class PlatformRuntime:
    def __init__(self, engine: AsyncEngine, approved_ids: frozenset[UUID]):
        self.engine, self.approved_ids = engine, approved_ids
        self.sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        self._ready = False
        self._readiness_lock = asyncio.Lock()

    async def ensure_ready(self) -> None:
        if not self.approved_ids:
            raise ApiError(ErrorCode.UNAVAILABLE)
        if self._ready:
            return
        async with self._readiness_lock:
            if self._ready:
                return
            try:
                report = await read_only_report(self.engine)
                if not all(
                    report[key]
                    for key in (
                        "expected_mariadb_11_4",
                        "expected_connection_collation",
                        "expected_schema",
                        "column_names_ready",
                    )
                ):
                    raise ApiError(ErrorCode.UNAVAILABLE)
            except Exception:
                raise ApiError(ErrorCode.UNAVAILABLE) from None
            self._ready = True

    async def bind(self, db: AsyncSession, student: StudentRow) -> BoundSession:
        return await db.run_sync(
            lambda sync: bind_student(sync, student, self.approved_ids, utc_now())
        )

    async def login(self, db: AsyncSession, student_id: str, password: str) -> LoginData:
        await self.ensure_ready()
        try:
            # Shared lock order: legacy student, token row (if present), canonical binding/rights.
            await db.get(StudentRow, student_id, with_for_update=True, populate_existing=True)
            student = await authenticate(db, student_id, password)
            if student is None:
                raise ApiError(ErrorCode.UNAUTHORIZED)
            binding = await self.bind(db, student)
            token = await issue_token(db, student.student_id, cleanup_student_only=True)
            return LoginData(
                token=token, student_id=student.student_id, name=binding.profile.display_name
            )
        except SQLAlchemyError:
            raise ApiError(ErrorCode.UNAVAILABLE) from None

    async def verify(self, db: AsyncSession, token: str | None) -> BoundSession:
        await self.ensure_ready()
        if not token or len(token) > 512:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        try:
            # Discover only the token's subject; after locking, resolve again before trusting it.
            student_id = await resolve_token(db, token)
            if student_id is None:
                raise ApiError(ErrorCode.UNAUTHORIZED)
            student = await db.get(
                StudentRow, student_id, with_for_update=True, populate_existing=True
            )
            locked_token = await db.get(
                AuthSessionRow, _token_hash(token), with_for_update=True, populate_existing=True
            )
            if (
                student is None
                or locked_token is None
                or await resolve_token(db, token) != student.student_id
            ):
                raise ApiError(ErrorCode.UNAUTHORIZED)
            return await self.bind(db, student)
        except SQLAlchemyError:
            raise ApiError(ErrorCode.UNAVAILABLE) from None

    async def context(self, token: str | None) -> BoundSession:
        async with self.sessions() as db, db.begin():
            return await self.verify(db, token)

    async def run(
        self, token: str, principal: VerifiedPrincipal, operation: Callable[[P0Services], T]
    ) -> T:
        async def verify_again(db: AsyncSession, expected: VerifiedPrincipal) -> None:
            current = await self.verify(db, token)
            if current.principal.user_id != expected.user_id:
                raise ApiError(ErrorCode.UNAUTHORIZED)

        return await P0Executor(self.engine, verify_principal=verify_again).run(
            principal, operation
        )

    async def personal(self, token: str, principal: VerifiedPrincipal, operation) -> T:
        async def verify_again(db: AsyncSession, expected: VerifiedPrincipal) -> None:
            current = await self.verify(db, token)
            if current.principal.user_id != expected.user_id:
                raise ApiError(ErrorCode.UNAUTHORIZED)

        return await P0Executor(self.engine, verify_principal=verify_again).run_personal(
            principal, operation
        )

    async def public(self, operation) -> T:
        await self.ensure_ready()
        return await P0Executor(self.engine).public_opportunities(operation)
