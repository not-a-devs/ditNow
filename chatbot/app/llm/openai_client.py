import logging
import time

import openai

from app.llm.base import ChatMessage, LLMAuthError, LLMClient, LLMError

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    """OpenAI 및 OpenAI 호환 서버(vLLM, Ollama 등) 클라이언트."""

    def __init__(self, model: str, api_key: str, timeout: float, base_url: str | None = None):
        # 타임아웃·네트워크·5xx는 SDK가 지수 백오프로 2회 재시도한다
        self.client = openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2
        )
        self.model = model

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        """메시지 목록을 보내고 답변 텍스트를 반환한다."""
        start = time.perf_counter()
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[m.model_dump() for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            raise LLMAuthError(f"인증 실패 ({type(e).__name__})") from e
        except openai.APIError as e:
            raise LLMError(f"OpenAI 호출 실패 ({type(e).__name__})") from e
        logger.info(
            "llm model=%s ms=%d tokens=%s",
            self.model,
            (time.perf_counter() - start) * 1000,
            resp.usage.total_tokens if resp.usage else None,
        )
        text = resp.choices[0].message.content if resp.choices else None
        if not text:
            raise LLMError("빈 응답")
        return text
