import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT_DIR
from app.intents import (
    CAMPUS,
    PERSONAL_INTENTS,
    classify_keywords,
    extract_day,
    route,
)
from app.llm import ChatMessage, LLMClient
from app.personal import (
    HANDLERS,
    KST,
    PersonalQuery,
    day_classes,
    exams,
    grades,
    my_courses,
    next_class,
    remaining_credits,
)
from app.retriever.keyword import KeywordRetriever
from app.schemas import CampusData, Student, StudentData
from tests.test_api import client  # noqa: F401  (픽스처 재사용)

MON = datetime(2026, 10, 26, tzinfo=KST)  # 월요일
Bundles = dict[str, tuple[Student, StudentData]]


def _at(day_offset: int, hhmm: str) -> datetime:
    """MON 기준 며칠 뒤 hh:mm."""
    h, m = map(int, hhmm.split(":"))
    return MON.replace(day=MON.day + day_offset, hour=h, minute=m)


def _q(now: datetime = MON, question: str = "", day: str | None = None) -> PersonalQuery:
    return PersonalQuery(question, now, day)


class _ScriptedLLM(LLMClient):
    """정해진 답을 돌려주고 호출을 기록하는 LLM."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], **_: object) -> str:
        self.calls.append(messages)
        return self.reply


def test_monday_fixture_is_monday() -> None:
    assert MON.weekday() == 0


def test_every_intent_has_handler() -> None:
    assert set(HANDLERS) == PERSONAL_INTENTS


@pytest.mark.parametrize(
    ("q", "intent"),
    [
        ("내 다음 수업 어디서 들어?", "next_class"),
        ("다음강의 몇시야", "next_class"),
        ("오늘 수업 뭐 있어", "day_classes"),
        ("내 시간표 알려줘", "day_classes"),
        ("목요일 수업 몇시야", "day_classes"),  # 요일이 있으면 다음 수업보다 시간표
        ("다음 수업 시간표", "next_class"),
        ("자료구조 강의실 어디야", "next_class"),
        (
            "웹프로그래밍 강의실은 어디야?",
            "next_class",
        ),  # 조사가 붙어도 (후속 질문 재작성에서 발견)
        ("오늘은 수업 뭐 있어", "day_classes"),
        ("졸업학점 몇 학점 남았어?", "remaining_credits"),
        ("졸업까지 얼마나 남았지", "remaining_credits"),
        ("이따 수업 몇 시야?", "next_class"),  # '수업'은 교무부 별칭이라 campus로 새던 표현
        ("학점 얼마나 더 따야 졸업해?", "remaining_credits"),
        ("내 학점 몇학점이야?", "remaining_credits"),  # /docs 수동 테스트에서 campus로 새던 표현
        ("오늘 수업 몇시에 끝나", "day_classes"),  # 정확한 표현이 조합 규칙보다 우선
        ("졸업증명서 어디서 뽑아", CAMPUS),  # 규칙 맨 위에서 교내 정보로 고정
        ("성적증명서 어디서 뽑아", CAMPUS),
        ("성적장학금 기준이 뭐야", CAMPUS),
        ("셔틀버스 시간표 알려줘", CAMPUS),  # 실제 말투 질문 세트에서 발견
        ("시험기간에 도서관 몇시까지 해", CAMPUS),
        ("성적 이의신청 어디서 해", CAMPUS),
        ("내 평점 몇이야", "grades"),
        ("지난 학기 성적 알려줘", "grades"),
        ("시험 성적 언제 나와", "grades"),  # 성적이 시험보다 우선
        ("기말고사 언제야", "exams"),
        ("데이터베이스 시험 어디서 봐", "exams"),
        ("이번 학기 듣는 과목 뭐야", "my_courses"),
        ("웹프로그래밍 교수님 누구야", "my_courses"),
    ],
)
def test_classify(q: str, intent: str) -> None:
    assert classify_keywords(q) == intent


@pytest.mark.parametrize("q", ["수강신청 언제야", "졸업식 언제야", "정보관 어디야"])
def test_no_rule(q: str) -> None:
    """규칙에 없는 질문은 None (route가 검색·LLM으로 판단)."""
    assert classify_keywords(q) is None


@pytest.mark.parametrize(
    ("q", "day"),
    [
        ("목요일 수업 뭐야", "목"),
        ("내일 수업 있어?", "내일"),
        ("이번 주 시간표", "week"),
        ("오늘 수업", "오늘"),
        ("다음 수업 어디야", None),
    ],
)
def test_extract_day(q: str, day: str | None) -> None:
    assert extract_day(q) == day


async def test_route_uses_llm_when_rules_miss(campus_data: CampusData) -> None:
    """규칙에 없는 1인칭 질문은 LLM이 분류하고, LLM이 준 값은 허용 목록 안에서만 쓴다."""
    retriever = KeywordRetriever(list(campus_data.facilities.values()))
    llm = _ScriptedLLM('{"intent": "day_classes", "day": "목", "student_id": "99999999"}')
    intent = await route("나 목욜에 뭐 들어?", retriever, llm)
    assert (intent.name, intent.day, intent.by) == ("day_classes", "목", "llm")

    weird = _ScriptedLLM('{"intent": "drop_table", "day": "someday"}')
    intent = await route("나 뭐 해야 돼?", retriever, weird)
    assert (intent.name, intent.day) == (CAMPUS, None)

    # 리스트처럼 해시 불가 값이 와도 500 없이 교내 질문으로 처리한다
    unhashable = _ScriptedLLM('{"intent": ["grades"], "day": {"x": 1}}')
    intent = await route("나 뭐 해야 돼?", retriever, unhashable)
    assert (intent.name, intent.day) == (CAMPUS, None)


async def test_route_skips_llm(campus_data: CampusData) -> None:
    """규칙에 맞거나, 1인칭 없이 교내 검색이 되는 질문은 LLM을 부르지 않는다."""
    retriever = KeywordRetriever(list(campus_data.facilities.values()))
    llm = _ScriptedLLM("{}")
    assert (await route("다음 수업 어디야", retriever, llm)).name == "next_class"
    assert (await route("학식 몇시까지 해", retriever, llm)).name == CAMPUS
    assert llm.calls == []


async def test_route_falls_back_when_llm_fails(campus_data: CampusData) -> None:
    """LLM이 JSON을 못 주면 교내 검색으로 간다."""
    retriever = KeywordRetriever(list(campus_data.facilities.values()))
    intent = await route("오늘 날씨 어때?", retriever, _ScriptedLLM("모르겠어요"))
    assert (intent.name, intent.by) == (CAMPUS, "keyword")


def test_eval_questions_stay_campus() -> None:
    """기존 교내 정보 평가 질문이 개인 질문으로 잘못 분류되지 않는다."""
    cases = json.loads((ROOT_DIR / "tests" / "eval_questions.json").read_text(encoding="utf-8"))
    assert [
        c["question"] for c in cases if classify_keywords(c["question"]) not in (None, CAMPUS)
    ] == []


@pytest.mark.parametrize(
    ("now", "course", "when"),
    [
        (_at(0, "09:00"), "CS201", "오늘"),  # 월 10:00 자료구조 전
        (_at(0, "10:30"), "CS205", "내일"),  # 자료구조 시작 후 → 화 웹프로그래밍
        (_at(3, "09:30"), "GE101", "내일"),  # 목 수업 중 → 금
        (_at(4, "16:00"), "CS201", "다음 주 월요일"),  # 금 마지막 수업 후
        (_at(5, "12:00"), "CS201", "다음 주 월요일"),  # 토
    ],
)
def test_next_class(
    students: Bundles, campus_data: CampusData, now: datetime, course: str, when: str
) -> None:
    [block], _ = next_class(*students["20231001"], campus_data, _q(now))
    assert block.startswith(f"[{course}] 다음 수업({when},")


def test_next_class_of_named_course(students: Bundles, campus_data: CampusData) -> None:
    """과목을 말하면 그 과목의 다음 수업 (월 09:00 → 데이터베이스는 목요일)."""
    [block], _ = next_class(
        *students["20231001"], campus_data, _q(question="데이터베이스 강의실 어디야")
    )
    assert block.startswith("[CS210]") and "정보관 702호" in block


def test_next_class_none(students: Bundles, campus_data: CampusData) -> None:
    """수강 과목이 없으면 없다고 알려 준다."""
    [block], _ = next_class(*students["20221003"], campus_data, _q())
    assert block.startswith("[my_timetable]")


def _ids(blocks: list[str]) -> list[str]:
    return [b[1 : b.index("]")] for b in blocks]


@pytest.mark.parametrize(
    ("day", "question", "expected", "label"),
    [
        (None, "오늘 수업", ["CS201"], "오늘(월요일)"),
        ("내일", "", ["CS205"], "내일(화요일)"),
        ("목", "", ["CS210"], "목요일"),
        ("week", "", ["CS201", "CS205", "CS201", "CS210", "GE101"], "이번 주"),
        (None, "자료구조 무슨 요일이야", ["CS201", "CS201"], "이번 주"),  # 과목만 → 그 과목 전체
    ],
)
def test_day_classes(
    students: Bundles,
    campus_data: CampusData,
    day: str | None,
    question: str,
    expected: list[str],
    label: str,
) -> None:
    blocks, _ = day_classes(*students["20231001"], campus_data, _q(question=question, day=day))
    assert _ids(blocks) == expected and f"{label} 수업" in blocks[0]


def test_day_classes_named_course_not_that_day(students: Bundles, campus_data: CampusData) -> None:
    """과목을 콕 집었는데 그날 수업이 없으면, 없다고 밝히고 그 과목의 일주일을 보여 준다."""
    blocks, _ = day_classes(
        *students["20231001"], campus_data, _q(question="내일 웹프로그래밍 강의실", day="목")
    )
    assert blocks[0] == "[my_timetable] 목요일에는 웹프로그래밍 수업이 없습니다."
    assert _ids(blocks)[1:] == ["CS205"] and "미래관 401호" in blocks[1]


def test_day_classes_none(students: Bundles, campus_data: CampusData) -> None:
    [none], _ = day_classes(*students["20231001"], campus_data, _q(_at(5, "08:00")))
    assert none.startswith("[my_timetable] 오늘(토요일)") and "수업이 없습니다" in none


def test_remaining_credits(students: Bundles, campus_data: CampusData) -> None:
    """졸업 80(전공 54·교양 12) - 취득 42(전공 30·교양 8·일반 4), 수강 중 11학점."""
    [block], _ = remaining_credits(*students["20231001"], campus_data, _q())
    assert "남은 학점: 총 38학점" in block
    assert "남은 전공: 24학점" in block and "남은 교양: 4학점" in block
    assert "모두 이수하면 남은 학점은 총 27학점" in block


def test_remaining_credits_done(students: Bundles, campus_data: CampusData) -> None:
    [block], _ = remaining_credits(*students["20221003"], campus_data, _q())
    assert "남은 학점: 총 0학점" in block and "남은 전공: 0학점 (충족)" in block


def _login(c: TestClient, student_id: str = "20231001", pw: str = "3000001") -> dict[str, str]:
    token = c.post("/auth/login", json={"student_id": student_id, "password": pw}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_personal_question_needs_login(client: TestClient) -> None:  # noqa: F811
    body = client.post("/ask", json={"question": "내 다음 수업 어디야"}).json()
    assert body["need_login"] is True and body["intent"] == "next_class"


def test_personal_question_with_login(client: TestClient) -> None:  # noqa: F811
    """로그인하면 본인 데이터로 답하고, 개인 답변은 캐시되지 않는다."""
    q = {"question": "졸업학점 몇 학점 남았어?"}
    body = client.post("/ask", json=q, headers=_login(client)).json()
    assert (body["intent"], body["sources"], body["need_login"]) == (
        "remaining_credits",
        ["my_credits"],
        False,
    )
    # 같은 질문을 비로그인으로 다시 해도 앞 학생의 답이 캐시에서 나오지 않는다
    assert client.post("/ask", json=q).json()["need_login"] is True


def test_invalid_token_is_401(client: TestClient) -> None:  # noqa: F811
    res = client.post("/ask", json={"question": "학식"}, headers={"Authorization": "Bearer x"})
    assert res.status_code == 401


def test_earned_credits_from_enrollments(students: Bundles) -> None:
    """취득 학점은 수강 이력에서 계산한다. F(CS111)와 수강 중 과목은 빠진다."""
    kim, data = students["20231001"]
    assert kim.earned_credits == {"전공": 30, "교양": 8, "일반": 4}
    assert kim.enrollments == ["CS201", "CS205", "CS210", "GE101"]
    assert set(data.courses) == set(kim.enrollments)


def test_my_courses(students: Bundles, campus_data: CampusData) -> None:
    """이번 학기 4과목 11학점, 과목을 말하면 그 과목만."""
    blocks, _ = my_courses(*students["20231001"], campus_data, _q())
    assert blocks[0] == "[my_courses] 이번 학기 수강: 4과목 11학점"
    assert _ids(blocks)[1:] == ["CS201", "CS205", "CS210", "GE101"]
    named, _ = my_courses(*students["20231001"], campus_data, _q(question="웹프로그래밍 교수님"))
    assert _ids(named) == ["my_courses", "CS205"] and "담당 최교수" in named[1]
    [none], _ = my_courses(*students["20221003"], campus_data, _q())
    assert "수강 과목이 없습니다" in none


def test_grades(students: Bundles, campus_data: CampusData) -> None:
    """평점은 학점 가중, F 포함 (원본 JSON에서 따로 계산한 값과 비교)."""
    [block], _ = grades(*students["20231001"], campus_data, _q())
    assert "- 전체 평점: 3.51 (45학점 기준, F 포함)" in block
    assert "- 2025-2학기 평점: 4.12 (13학점)" in block
    assert "최근 학기(2026-1) 과목별 성적" in block and "알고리즘 (2026-1, 전공 3학점): F" in block


def test_grades_named_course(students: Bundles, campus_data: CampusData) -> None:
    """수강 중인 과목은 아직 성적 없음, 지난 과목은 그 성적."""
    [now], _ = grades(*students["20231001"], campus_data, _q(question="자료구조 성적"))
    assert "자료구조 (2026-2, 전공 3학점): 아직 성적 없음(수강 중)" in now
    [past], _ = grades(*students["20231001"], campus_data, _q(question="알고리즘 성적 몇이야"))
    assert "알고리즘 (2026-1, 전공 3학점): F" in past


def test_exams(students: Bundles, campus_data: CampusData) -> None:
    """기본은 남은 시험(월 10/26 기준 기말 4개), '중간'을 말하면 지난 중간고사도."""
    blocks, _ = exams(*students["20231001"], campus_data, _q())
    assert _ids(blocks) == ["CS201", "CS205", "CS210", "GE101"]
    assert "2026-12-14 (월요일) 10:00~11:00 (D-49" in blocks[0]
    mid, _ = exams(*students["20231001"], campus_data, _q(question="중간고사 언제였어"))
    assert all("중간고사" in b and "이미 지난 시험" in b for b in mid) and len(mid) == 3
    [db_exam], _ = exams(*students["20231001"], campus_data, _q(question="데이터베이스 시험 어디"))
    assert db_exam.startswith("[CS210] 기말고사") and "정보관 702호" in db_exam


def test_new_intents_via_api(client: TestClient) -> None:  # noqa: F811
    """새 질문 종류가 로그인 후 /ask에서 근거와 함께 답한다."""
    headers = _login(client)
    for q, intent, source in [
        ("내 평점 몇이야", "grades", "my_grades"),
        ("이번 학기 듣는 과목 뭐야", "my_courses", "my_courses"),
    ]:
        body = client.post("/ask", json={"question": q}, headers=headers).json()
        assert (body["intent"], source in body["sources"]) == (intent, True)
