"""질문 의도 분류: 키워드 규칙 먼저, 애매하면 LLM이 보조한다."""

import json
import logging
import re

from pydantic import BaseModel

from app.llm import ChatMessage, LLMClient, LLMError
from app.prompt import CLASSIFY_PROMPT
from app.retriever.base import Retriever
from app.retriever.keyword import normalize, tokenize
from app.schemas import WEEKDAYS

logger = logging.getLogger(__name__)

CAMPUS = "campus"
WEEK = "week"

# (띄어쓰기 뺀 표현, 의도). 위에서부터 처음 맞는 규칙을 쓴다. 'A+B'는 A와 B가 모두 있으면 일치
RULES: list[tuple[str, str]] = [
    # 개인 키워드와 겹치지만 교내 정보인 표현
    ("증명서", CAMPUS),  # 성적증명서·졸업증명서
    ("장학", CAMPUS),  # 성적장학금
    ("이의신청", CAMPUS),  # 성적 이의신청
    ("시험기간", CAMPUS),  # 시험기간 도서관 운영
    ("버스", CAMPUS),  # 셔틀버스 시간표
    ("셔틀", CAMPUS),
    # 성적·평점
    ("평점", "grades"),
    ("평균학점", "grades"),
    ("학점평균", "grades"),
    ("gpa", "grades"),
    ("성적", "grades"),
    # 시험
    ("중간고사", "exams"),
    ("기말고사", "exams"),
    ("기말", "exams"),
    ("시험", "exams"),
    # 이번 학기 수강 과목·교수
    ("수강과목", "my_courses"),
    ("수강중", "my_courses"),
    ("수강신청한", "my_courses"),
    ("듣는과목", "my_courses"),
    ("듣는수업", "my_courses"),
    ("듣는강의", "my_courses"),
    ("교수님", "my_courses"),
    ("교수+누구", "my_courses"),
    ("몇학점짜리", "my_courses"),
    ("과목+뭐", "my_courses"),
    # 다음 수업 (분명한 표현)
    ("다음수업", "next_class"),
    ("다음강의", "next_class"),
    ("다음교시", "next_class"),
    # 요일별 시간표 ('다음 수업 시간표'는 위에서 next_class)
    ("시간표", "day_classes"),
    ("오늘수업", "day_classes"),
    ("오늘강의", "day_classes"),
    ("내일수업", "day_classes"),
    ("모레수업", "day_classes"),
    ("요일+수업", "day_classes"),
    ("요일+강의", "day_classes"),
    ("이번주+수업", "day_classes"),
    # 다음 수업 (느슨한 표현: '목요일 수업 몇시야'는 위에서 day_classes)
    ("수업어디", "next_class"),
    ("강의실어디", "next_class"),
    ("수업+몇시", "next_class"),
    ("수업+언제", "next_class"),
    # 학점·졸업
    ("졸업+학점", "remaining_credits"),
    ("남은학점", "remaining_credits"),
    ("학점남", "remaining_credits"),
    ("졸업까지", "remaining_credits"),
    ("졸업요건", "remaining_credits"),
    ("이수학점", "remaining_credits"),
    ("내학점", "remaining_credits"),
    ("취득학점", "remaining_credits"),
]
PERSONAL_INTENTS = {intent for _, intent in RULES} - {CAMPUS}

# 조건값: 요일
_DAY = re.compile(r"([월화수목금토일])요일|(오늘|내일|모레)|(이번\s*주|일주일|주간|전체\s*시간표)")
VALID_DAYS = {*WEEKDAYS, "오늘", "내일", "모레", WEEK}

# '내 ~', '제 ~' 같은 1인칭이 있으면 개인 질문일 가능성이 높다
# 분류 답은 JSON 한 줄이지만, 최신 모델은 답 전에 추론 토큰을 써서 200일 때 빈 응답이 왔다
CLASSIFY_MAX_TOKENS = 1024

_FIRST_PERSON = {"내", "나", "제", "저", "내가", "나는", "제가", "저는", "나의", "저의", "내꺼"}


class Intent(BaseModel):
    """분류 결과."""

    name: str
    day: str | None = None  # "월"~"일" | "오늘" | "내일" | "모레" | "week"
    by: str = "keyword"  # keyword | llm


def extract_day(question: str) -> str | None:
    """질문에서 요일 조건을 뽑는다."""
    m = _DAY.search(question)
    if m is None:
        return None
    return m.group(1) or m.group(2) or WEEK


def classify_keywords(question: str) -> str | None:
    """규칙에 맞는 의도. 어떤 규칙에도 안 맞으면 None."""
    # 단어 끝 조사를 떼야 '강의실은 어디야'가 '강의실어디' 규칙에 맞는다
    compact = "".join(tokenize(question))
    for keyword, intent in RULES:
        if all(part in compact for part in keyword.split("+")):
            return intent
    return None


async def classify_with_llm(question: str, llm: LLMClient) -> Intent | None:
    """LLM에 의도·요일을 JSON으로 묻는다. 실패하면 None."""
    messages = [
        ChatMessage(role="system", content=CLASSIFY_PROMPT),
        ChatMessage(role="user", content=question),
    ]
    try:
        raw = await llm.chat(messages, temperature=0, max_tokens=CLASSIFY_MAX_TOKENS)
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        data = json.loads(match.group(0)) if match else None
    except (LLMError, json.JSONDecodeError) as e:
        logger.warning("LLM 의도 분류 실패: %s", e)
        return None
    if not isinstance(data, dict):
        return None
    # LLM이 고른 값은 정해진 목록 안에서만 받는다 (학번 같은 다른 값은 쓰지 않는다)
    name = data.get("intent")
    day = data.get("day")
    return Intent(
        name=name if name in PERSONAL_INTENTS else CAMPUS,
        day=day if day in VALID_DAYS else None,
        by="llm",
    )


async def route(question: str, retriever: Retriever, llm: LLMClient) -> Intent:
    """키워드 규칙으로 분류하고, 규칙에 없으면서 개인 질문 같거나 검색이 안 되면 LLM에 묻는다."""
    day = extract_day(question)
    name = classify_keywords(question)
    if name is not None:
        return Intent(name=name, day=day)
    first_person = bool(set(normalize(question).split()) & _FIRST_PERSON)
    if first_person or not retriever.search(question, 1):
        llm_intent = await classify_with_llm(question, llm)
        if llm_intent is not None:
            return llm_intent
    return Intent(name=CAMPUS, day=day)
