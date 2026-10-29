"""챗봇 RAG(의도 분류·검색·개인 질문·LLM 답변)와 학번 로그인을 통합 API에 연결한다.

챗봇 코드를 복제하지 않고 패키지 함수를 그대로 호출한다. 서버 시작 시 테이블·시드를 만들지 않는다.
legacy 학번 원장은 공통 UUID·현재 학적 bridge 승인 전이라 `environment=test`의 정확한 격리
메모리 DB에서만 쓴다. 그 외 환경의 로그인·토큰 개인 질문은 503이며, `app.seed_demo`도 격리
메모리 이외 대상을 연결 전에 거부한다(원격 테이블 생성·시드 명령이 아니다).
"""

import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from importlib.resources import as_file, files

from chatbot.app.auth import authenticate, issue_token, resolve_token, revoke_token
from chatbot.app.config import Settings as ChatbotSettings
from chatbot.app.conversation import condense
from chatbot.app.data_loader import load_data
from chatbot.app.db import make_engine
from chatbot.app.intents import CAMPUS, route
from chatbot.app.llm import LLMClient, get_llm_client
from chatbot.app.rag import answer_question
from chatbot.app.retriever.keyword import KeywordRetriever
from chatbot.app.schemas import CampusData, Turn
from chatbot.app.student_repo import load_student
from fastapi import Request
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.ai import AskData, AskInput
from app.schemas.auth import LoginData
from app.schemas.common import ErrorCode


@dataclass
class Assistant:
    """앱 하나에 하나. 시설 인덱스·LLM 클라이언트·DB 연결을 재사용한다."""

    campus: CampusData
    retriever: KeywordRetriever
    llm: LLMClient | None
    engine: AsyncEngine | None
    semester: str
    rate_limit_per_min: int
    # shortcut: IP별 요청 기록이 프로세스 메모리에만 있음(워커 1개 전제), 다중 워커면 Redis로
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def __post_init__(self) -> None:
        # expire_on_commit=False: 토큰 저장(commit) 뒤 학생 이름을 읽을 때 비동기 지연 조회가 없게
        self._sessions = (
            async_sessionmaker(self.engine, expire_on_commit=False) if self.engine else None
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessions is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        async with self._sessions() as db:
            yield db

    def check_rate_limit(self, client_ip: str) -> None:
        """IP당 분당 요청 수 제한 (LLM 비용 폭주·비밀번호 대입 완화)."""
        now = time.monotonic()
        hits = self._hits[client_ip]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.rate_limit_per_min:
            raise ApiError(ErrorCode.RATE_LIMITED)
        hits.append(now)

    async def login(self, db: AsyncSession, student_id: str, password: str) -> LoginData:
        student = await authenticate(db, student_id, password)
        if student is None:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        token = await issue_token(db, student.student_id)
        return LoginData(token=token, student_id=student.student_id, name=student.name)

    async def student_id(self, db: AsyncSession | None, token: str | None) -> str | None:
        """토큰이 없으면 비로그인(None), 잘못됐거나 만료됐으면 401."""
        if token is None:
            return None
        if db is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        student_id = await resolve_token(db, token)
        if student_id is None:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        return student_id

    async def logout(self, db: AsyncSession, token: str) -> None:
        await revoke_token(db, token)

    async def ask(self, body: AskInput, db: AsyncSession | None, student_id: str | None) -> AskData:
        if self.llm is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        question = body.question.strip()
        if not any(character.isalnum() for character in question):
            raise ApiError(ErrorCode.VALIDATION)
        rewritten = None
        if body.history:
            turns = [Turn(role=t.role, content=t.content) for t in body.history]
            question = await condense(turns, question, self.llm)
            rewritten = question if question != body.question.strip() else None
        intent = await route(question, self.retriever, self.llm)
        bundle = None
        # 학번은 항상 서버가 검증한 토큰에서만 온다. 교내 질문이면 학적을 읽지 않는다
        if student_id and db is not None and intent.name != CAMPUS:
            bundle = await load_student(db, student_id, self.semester)
        res = await answer_question(
            question,
            retriever=self.retriever,
            llm=self.llm,
            data=self.campus,
            student=bundle[0] if bundle else None,
            student_data=bundle[1] if bundle else None,
            intent=intent,
        )
        return AskData(
            answer=res.answer,
            sources=res.sources,
            locations=[loc.model_dump() for loc in res.locations],
            found=res.found,
            intent=res.intent,
            need_login=res.need_login,
            classified_by=res.classified_by,
            rewritten_question=rewritten,
            personal_data_access=bundle is not None,
        )


class IntegratedLLMSettings(ChatbotSettings):
    """통합 API가 넘긴 값만 쓰는 챗봇 설정. 환경 변수·.env·secret 파일을 읽지 않는다.

    `_env_file=None`은 .env만 끄고 접두사 없는 `DATABASE_URL`·`DB_AUTO_INIT` 등은 여전히 읽으므로,
    입력 소스를 생성자 인자로 한정한다. 필드 검증기는 그대로 실행된다.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def chatbot_llm_settings(settings: Settings) -> IntegratedLLMSettings:
    return IntegratedLLMSettings(
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_api_key=settings.llm_api_key,
        llm_base_url=settings.llm_base_url,
        llm_timeout_sec=settings.llm_timeout_sec,
    )


def build_assistant(settings: Settings) -> Assistant:
    """설정에서 Assistant를 만든다. DB·LLM 연결은 실제 요청 때 맺는다."""
    with as_file(files("chatbot").joinpath("data")) as data_dir:
        campus = load_data(data_dir)
    llm = get_llm_client(chatbot_llm_settings(settings)) if settings.llm_provider else None
    url = settings.database_url.get_secret_value() if settings.database_url else ""
    # This legacy student/session ledger has no approved common UUID/current-grant bridge.
    # Even an approved DB engine alone must not activate it. Only isolated test memory is allowed.
    memory_demo = settings.environment == "test" and url == "sqlite+aiosqlite:///:memory:"
    return Assistant(
        campus=campus,
        retriever=KeywordRetriever(list(campus.facilities.values())),
        llm=llm,
        engine=make_engine(url) if memory_demo else None,
        semester=settings.current_semester,
        rate_limit_per_min=settings.ask_rate_limit_per_min,
    )


def get_assistant(request: Request) -> Assistant:
    return request.app.state.assistant
