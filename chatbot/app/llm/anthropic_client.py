import logging
import time

import anthropic

from app.llm.base import ChatMessage, LLMAuthError, LLMClient, LLMError

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClient):
    """Anthropic Claude 클라이언트."""

    def __init__(self, model: str, api_key: str, timeout: float):
        # 타임아웃·네트워크·429·5xx는 SDK가 지수 백오프로 2회 재시도한다
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        """메시지 목록을 보내고 답변 텍스트를 반환한다.

        최신 Claude 모델은 temperature를 받지 않아(400) 전달하지 않는다.
        """
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        chat = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        start = time.perf_counter()
        try:
            resp = await self.client.messages.create(
                model=self.model, system=system, messages=chat, max_tokens=max_tokens
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise LLMAuthError(f"인증 실패 ({type(e).__name__})") from e
        except anthropic.APIError as e:
            raise LLMError(f"Anthropic 호출 실패 ({type(e).__name__})") from e
        logger.info(
            "llm model=%s ms=%d in=%d out=%d stop=%s",
            self.model,
            (time.perf_counter() - start) * 1000,
            resp.usage.input_tokens,
            resp.usage.output_tokens,
            resp.stop_reason,
        )
        if resp.stop_reason == "refusal":
            raise LLMError("모델이 답변을 거절함")
        text = "".join(b.text for b in resp.content if b.type == "text")
        if not text:
            raise LLMError(f"빈 응답 (stop={resp.stop_reason})")
        return text
