import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT_DIR
from app.intents import CAMPUS, INTENT_KEYWORDS, classify
from app.personal import HANDLERS, KST, next_class, remaining_credits, today_classes
from app.schemas import CampusData, StudentData
from tests.test_api import client  # noqa: F401  (픽스처 재사용)

MON = datetime(2026, 10, 26, tzinfo=KST)  # 월요일


def _at(day_offset: int, hhmm: str) -> datetime:
    """MON 기준 며칠 뒤 hh:mm."""
    h, m = map(int, hhmm.split(":"))
    return MON.replace(day=MON.day + day_offset, hour=h, minute=m)


def test_monday_fixture_is_monday() -> None:
    assert MON.weekday() == 0


def test_every_intent_has_handler() -> None:
    assert set(HANDLERS) == set(INTENT_KEYWORDS)


@pytest.mark.parametrize(
    ("q", "intent"),
    [
        ("내 다음 수업 어디서 들어?", "next_class"),
        ("다음강의 몇시야", "next_class"),
        ("오늘 수업 뭐 있어", "today_classes"),
        ("내 시간표 알려줘", "today_classes"),
        ("졸업학점 몇 학점 남았어?", "remaining_credits"),
        ("졸업까지 얼마나 남았지", "remaining_credits"),
        ("이따 수업 몇 시야?", "next_class"),  # '수업'은 교무부 별칭이라 campus로 새던 표현
        ("학점 얼마나 더 따야 졸업해?", "remaining_credits"),
        ("오늘 수업 몇시에 끝나", "today_classes"),  # 정확한 표현이 조합 규칙보다 우선
        ("수강신청 언제야", CAMPUS),
        ("졸업식 언제야", CAMPUS),
        ("졸업증명서 어디서 뽑아", CAMPUS),
        ("정보관 어디야", CAMPUS),
    ],
)
def test_classify(q: str, intent: str) -> None:
    assert classify(q) == intent


def test_eval_questions_stay_campus() -> None:
    """기존 교내 정보 평가 질문이 개인 질문으로 잘못 분류되지 않는다."""
    cases = json.loads((ROOT_DIR / "tests" / "eval_questions.json").read_text(encoding="utf-8"))
    assert [c["question"] for c in cases if classify(c["question"]) != CAMPUS] == []


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
    student_data: StudentData, campus_data: CampusData, now: datetime, course: str, when: str
) -> None:
    [block], _ = next_class(student_data.students["20231001"], student_data, campus_data, now)
    assert block.startswith(f"[{course}] 다음 수업({when},")


def test_next_class_none(student_data: StudentData, campus_data: CampusData) -> None:
    """수강 과목이 없으면 없다고 알려 준다."""
    [block], _ = next_class(student_data.students["20221003"], student_data, campus_data, MON)
    assert block.startswith("[my_timetable]")


def test_today_classes(student_data: StudentData, campus_data: CampusData) -> None:
    kim = student_data.students["20231001"]
    blocks, _ = today_classes(kim, student_data, campus_data, _at(0, "08:00"))
    assert [b.split("]")[0] for b in blocks] == ["[CS201"]
    [none], _ = today_classes(kim, student_data, campus_data, _at(5, "08:00"))
    assert "수업이 없습니다" in none


def test_remaining_credits(student_data: StudentData, campus_data: CampusData) -> None:
    """졸업 80(전공 54·교양 12) - 취득 42(전공 30·교양 8·일반 4), 수강 중 11학점."""
    [block], _ = remaining_credits(
        student_data.students["20231001"], student_data, campus_data, MON
    )
    assert "남은 학점: 총 38학점" in block
    assert "남은 전공: 24학점" in block and "남은 교양: 4학점" in block
    assert "모두 이수하면 남은 학점은 총 27학점" in block


def test_remaining_credits_done(student_data: StudentData, campus_data: CampusData) -> None:
    [block], _ = remaining_credits(
        student_data.students["20221003"], student_data, campus_data, MON
    )
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
