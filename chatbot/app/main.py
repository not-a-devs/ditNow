import logging
import secrets
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.data_loader import DataError, load_data
from app.llm import get_llm_client
from app.prompt import LLM_FAILURE_ANSWER
from app.rag import answer_question
from app.retriever.keyword import KeywordRetriever, normalize
from app.schemas import AskRequest, AskResponse, Facility

logger = logging.getLogger(__name__)
CACHE_TTL_SEC = 600


def _load_state(app: FastAPI, settings: Settings) -> None:
    """데이터를 읽고 검색기를 만들어 app.state에 보관한다. 데이터가 틀리면 DataError."""
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
        yield

    app = FastAPI(title="DIT NOW RAG", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

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

    @app.get("/health")
    def health() -> dict[str, object]:
        """서버·데이터 로드 상태."""
        return {"status": "ok", "facilities": len(app.state.data.facilities)}

    @app.post("/ask")
    async def ask(body: AskRequest, request: Request) -> AskResponse:
        """질문에 교내 데이터 근거로 답한다."""
        key = " ".join(normalize(body.question).split())
        if not key:
            raise HTTPException(422, "질문을 입력해 주세요.")
        cached = app.state.cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        check_rate_limit(request)
        res = await answer_question(
            body.question,
            retriever=app.state.retriever,
            llm=app.state.llm,
            data=app.state.data,
            top_k=settings.top_k,
            max_context_chars=settings.max_context_chars,
        )
        if res.answer != LLM_FAILURE_ANSWER:
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

    @app.post("/admin/reload")
    def reload_data(x_admin_token: str = Header(default="")) -> dict[str, object]:
        """data/ JSON을 다시 읽는다. ADMIN_TOKEN이 비어 있으면 비활성."""
        if not settings.admin_token or not secrets.compare_digest(
            x_admin_token, settings.admin_token
        ):
            raise HTTPException(403, "권한이 없어요.")
        try:
            _load_state(app, settings)
        except DataError as e:
            # 검증 실패 시 기존 데이터를 그대로 유지한다
            raise HTTPException(400, str(e)) from e
        logger.info("데이터 다시 로드: %d건", len(app.state.data.facilities))
        return {"status": "reloaded", "facilities": len(app.state.data.facilities)}

    return app


app = create_app()
