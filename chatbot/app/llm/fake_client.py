import re

from app.llm.base import ChatMessage, LLMClient

_CONTEXT_ID = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)


class FakeLLMClient(LLMClient):
    """테스트 전용. 컨텍스트 문서 id를 그대로 근거로 돌려준다."""

    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        """받은 컨텍스트의 문서 id를 [근거: ...] 줄로 붙여 반환한다."""
        self.calls.append(messages)
        ids = _CONTEXT_ID.findall(messages[-1].content)
        return f"테스트 답변입니다.\n[근거: {', '.join(ids)}]"
