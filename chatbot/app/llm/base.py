from abc import ABC, abstractmethod

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """LLM에 보내는 메시지 한 개."""

    role: str  # "system" | "user" | "assistant"
    content: str


class LLMError(Exception):
    """LLM 호출이 최종 실패했을 때 발생한다."""


class LLMAuthError(LLMError):
    """API 키 오류(401/403). 재시도하지 않는다."""


class LLMClient(ABC):
    """파이프라인이 사용하는 공급자 중립 인터페이스."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        """메시지 목록을 보내고 답변 텍스트를 반환한다."""
