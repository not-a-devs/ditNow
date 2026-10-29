from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.conversation import condense
from app.llm import ChatMessage, LLMClient, LLMError
from app.schemas import Turn
from tests.test_api import client  # noqa: F401  (픽스처 재사용)

HISTORY = [
    Turn(role="user", content="정보관 어디야?"),
    Turn(role="assistant", content="정보관은 도서관 건물이에요."),
]


class _SequenceLLM(LLMClient):
    """정해진 답을 순서대로 돌려주는 LLM. 예외를 넣으면 그 차례에 던진다."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], **_: object) -> str:
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('"정보관 편의점 몇 시까지 해?"\n(설명: 거기=정보관)', "정보관 편의점 몇 시까지 해?"),
        ("", "거기 몇 시까지 해?"),  # 빈 응답이면 원래 질문
        (LLMError("x"), "거기 몇 시까지 해?"),  # 실패하면 원래 질문
    ],
)
async def test_condense(reply: str | Exception, expected: str) -> None:
    """첫 줄만, 따옴표 없이 쓴다. 실패·빈 응답이면 원래 질문으로 진행한다."""
    llm = _SequenceLLM(reply)
    assert await condense(HISTORY, "거기 몇 시까지 해?", llm) == expected
    assert "정보관 어디야?" in llm.calls[0][-1].content  # 대화 기록이 프롬프트에 들어간다


def _history(place: str) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": f"{place} 어디야?"},
        {"role": "assistant", "content": f"{place} 위치를 알려 드렸어요."},
    ]


@pytest.fixture
def chat_client(client: TestClient) -> Iterator[TestClient]:  # noqa: F811
    """LLM을 _SequenceLLM으로 바꾼 테스트 서버."""
    original = client.app.state.llm
    yield client
    client.app.state.llm = original


def test_follow_up_uses_rewritten_question(chat_client: TestClient) -> None:
    """후속 질문은 바꾼 질문으로 검색·답변하고, 응답에 바꾼 질문을 알려 준다."""
    chat_client.app.state.llm = _SequenceLLM("정보관 몇 시까지 열어?", "답\n[근거: bld_jeongbo]")
    body = chat_client.post(
        "/ask", json={"question": "거기 몇 시까지 열어?", "history": _history("정보관")}
    ).json()
    assert body["rewritten_question"] == "정보관 몇 시까지 열어?"
    assert body["sources"] == ["bld_jeongbo"]


def test_same_follow_up_different_history(chat_client: TestClient) -> None:
    """같은 '거기 전화번호'도 대화가 다르면 캐시를 섞지 않고 각자 답한다."""
    chat_client.app.state.llm = _SequenceLLM(
        "학생식당 전화번호 알려줘",
        "답\n[근거: fac_cafeteria]",
        "컴소과 전화번호 알려줘",
        "답\n[근거: dept_cs]",
    )
    q = "거기 전화번호 알려줘"
    first = chat_client.post("/ask", json={"question": q, "history": _history("학식")}).json()
    second = chat_client.post("/ask", json={"question": q, "history": _history("컴소과")}).json()
    assert (first["sources"], second["sources"]) == (["fac_cafeteria"], ["dept_cs"])


def test_history_limit(chat_client: TestClient) -> None:
    """대화 기록은 6턴까지만 받는다."""
    turns = _history("정보관") * 4
    res = chat_client.post("/ask", json={"question": "거기 어디야", "history": turns})
    assert res.status_code == 422
