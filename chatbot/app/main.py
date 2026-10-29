import logging
import secrets
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import authenticate, issue_token, now_utc, resolve_token, revoke_token
from app.config import Settings, get_settings
from app.conversation import condense
from app.data_loader import DataError, load_data, load_mock_data
from app.db import init_db, make_engine
from app.intents import CAMPUS, route
from app.llm import get_llm_client
from app.models import QuestionLogRow
from app.prompt import LLM_FAILURE_ANSWER
from app.rag import answer_question
from app.retriever.keyword import KeywordRetriever, normalize
from app.schemas import (
    AskRequest,
    AskResponse,
    Facility,
    LoginRequest,
    LoginResponse,
    QuestionLogOut,
)
from app.student_repo import load_student

logger = logging.getLogger(__name__)
CACHE_TTL_SEC = 600

# Authorization을 일반 Header로 받으면 /docs(Swagger)가 보내지 않는다.
# 보안 스킴으로 받아야 /docs에 Authorize 버튼이 생긴다. auto_error=False: 비로그인 교내 질문 허용
bearer = HTTPBearer(auto_error=False, description="/auth/login에서 받은 token")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def _load_state(app: FastAPI, settings: Settings) -> None:
    """교내 데이터를 읽고 검색기를 만들어 app.state에 보관한다. 데이터가 틀리면 DataError."""
    data = load_data(settings.data_dir)
    app.state.data = data
    app.state.retriever = KeywordRetriever(list(data.facilities.values()), settings.min_score)
    app.state.cache = {}


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI 앱을 만든다. 테스트에서는 settings를 주입한다."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _load_state(app, settings)
        app.state.llm = get_llm_client(settings)
        app.state.hits = defaultdict(deque)
        engine = make_engine(settings.database_url)
        if settings.db_auto_init:
            mock = load_mock_data(settings.mock_dir, app.state.data)
            if await init_db(engine, mock):
                logger.info("DB가 비어 있어 목업 데이터를 넣었습니다")
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        yield
        await engine.dispose()

    app = FastAPI(title="DIT NOW RAG", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    async def get_db() -> AsyncIterator[AsyncSession]:
        """요청마다 DB 세션을 하나 연다."""
        async with app.state.sessionmaker() as db:
            yield db

    DB = Annotated[AsyncSession, Depends(get_db)]

    def check_rate_limit(request: Request) -> None:
        """IP당 분당 요청 수를 제한한다 (시연 중 LLM 비용 폭주 방지)."""
        # shortcut: IP별 기록이 메모리에만 쌓임(단일 프로세스 전제), 다중 워커·장기 운영 시 Redis로
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = app.state.hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_min:
            raise HTTPException(429, "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
        q.append(now)

    def require_admin(token: str) -> None:
        """ADMIN_TOKEN이 맞는지 확인한다. 비어 있으면 관리자 기능은 꺼져 있다."""
        if not settings.admin_token or not secrets.compare_digest(token, settings.admin_token):
            raise HTTPException(403, "권한이 없어요.")

    async def log_question(db: AsyncSession, question: str, res: AskResponse) -> None:
        """질문 결과를 남긴다. 로그 실패가 답변을 막지 않게 한다."""
        try:
            db.add(
                QuestionLogRow(
                    created_at=now_utc(),
                    question=question[:200],
                    rewritten_question=res.rewritten_question,
                    intent=res.intent,
                    classified_by=res.classified_by,
                    found=res.found,
                    need_login=res.need_login,
                    latency_ms=res.latency_ms,
                )
            )
            await db.commit()
        except SQLAlchemyError:
            logger.exception("질문 로그 저장 실패")
            await db.rollback()

    @app.post("/auth/login")
    async def login(body: LoginRequest, request: Request, db: DB) -> LoginResponse:
        """학번·초기 비밀번호(주민등록번호 뒷자리)로 로그인하고 토큰을 발급한다."""
        check_rate_limit(request)  # 비밀번호 대입 공격 완화
        student = await authenticate(db, body.student_id, body.password)
        if student is None:
            raise HTTPException(401, "학번 또는 비밀번호가 올바르지 않아요.")
        token = await issue_token(db, student.student_id)
        return LoginResponse(token=token, student_id=student.student_id, name=student.name)

    @app.post("/auth/logout")
    async def logout(creds: Credentials, db: DB) -> dict[str, str]:
        """토큰을 폐기한다."""
        if creds:
            await revoke_token(db, creds.credentials)
        return {"status": "ok"}

    @app.get("/health")
    async def health(db: DB) -> dict[str, object]:
        """서버·데이터·DB 연결 상태."""
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "facilities": len(app.state.data.facilities), "db": "ok"}

    async def current_student_id(
        db: AsyncSession, creds: HTTPAuthorizationCredentials | None
    ) -> str | None:
        """Bearer 토큰의 학번. 토큰이 없으면 비로그인(None), 잘못됐거나 만료됐으면 401."""
        if creds is None:
            return None
        student_id = await resolve_token(db, creds.credentials)
        if student_id is None:
            raise HTTPException(401, "로그인이 만료됐어요. 다시 로그인해 주세요.")
        return student_id

    @app.post("/ask")
    async def ask(body: AskRequest, request: Request, creds: Credentials, db: DB) -> AskResponse:
        """질문에 답한다. 개인 질문(시간표·학점)은 로그인 토큰이 필요하다.

        history가 있으면 후속 질문('거기 몇 시까지 해?')을 완전한 질문으로 바꿔 처리한다.
        """
        student_id = await current_student_id(db, creds)
        if not normalize(body.question).strip():
            raise HTTPException(422, "질문을 입력해 주세요.")
        question = body.question
        rewritten = None
        if body.history:
            check_rate_limit(request)  # 재작성도 LLM 호출이라 캐시보다 먼저 센다
            question = await condense(body.history, body.question, app.state.llm)
            rewritten = question if question != body.question else None
        # 캐시 키는 실제로 처리할 질문 기준 (같은 '거기 몇 시까지?'도 대화마다 다르다)
        # 캐시에는 교내 정보 답변만 들어 있어 학생 간에 개인 정보가 섞이지 않는다
        key = " ".join(normalize(question).split())
        cached = app.state.cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1].model_copy(update={"rewritten_question": rewritten})
        if not body.history:
            check_rate_limit(request)
        intent = await route(question, app.state.retriever, app.state.llm)
        # 교내 질문이면 학생 데이터를 읽지 않는다 (DB 조회 절약)
        bundle = None
        if student_id and intent.name != CAMPUS:
            bundle = await load_student(db, student_id, settings.current_semester)
        res = await answer_question(
            question,
            retriever=app.state.retriever,
            llm=app.state.llm,
            data=app.state.data,
            top_k=settings.top_k,
            max_context_chars=settings.max_context_chars,
            student=bundle[0] if bundle else None,
            student_data=bundle[1] if bundle else None,
            intent=intent,
        )
        res.rewritten_question = rewritten
        await log_question(db, body.question, res)
        if res.intent == CAMPUS and res.answer != LLM_FAILURE_ANSWER:
            # shortcut: 만료 항목을 지우지 않음, 질문 종류가 많아지면 크기 제한 LRU로
            app.state.cache[key] = (time.monotonic() + CACHE_TTL_SEC, res)
        return res

    @app.get("/facilities")
    def list_facilities() -> list[Facility]:
        """시설 목록 (프론트 지도 표시용)."""
        return list(app.state.data.facilities.values())

    @app.get("/facilities/{facility_id}")
    def get_facility(facility_id: str) -> Facility:
        """시설 상세."""
        fac = app.state.data.facilities.get(facility_id)
        if fac is None:
            raise HTTPException(404, "시설을 찾을 수 없어요.")
        return fac

    @app.get("/admin/questions")
    async def question_logs(
        db: DB, x_admin_token: str = Header(default=""), only_failed: bool = True, limit: int = 100
    ) -> list[QuestionLogOut]:
        """최근 질문 로그. only_failed면 답을 못 찾은 질문(로그인 요구 제외)만."""
        require_admin(x_admin_token)
        query = select(QuestionLogRow).order_by(QuestionLogRow.id.desc()).limit(min(limit, 500))
        if only_failed:
            query = query.where(~QuestionLogRow.found, ~QuestionLogRow.need_login)
        return [QuestionLogOut.model_validate(r) for r in await db.scalars(query)]

    @app.post("/admin/reload")
    def reload_data(x_admin_token: str = Header(default="")) -> dict[str, object]:
        """data/ JSON을 다시 읽는다. ADMIN_TOKEN이 비어 있으면 비활성."""
        require_admin(x_admin_token)
        try:
            _load_state(app, settings)
        except DataError as e:
            # 검증 실패 시 기존 데이터를 그대로 유지한다
            raise HTTPException(400, str(e)) from e
        logger.info("데이터 다시 로드: %d건", len(app.state.data.facilities))
        return {"status": "reloaded", "facilities": len(app.state.data.facilities)}

    return app


app = create_app()
