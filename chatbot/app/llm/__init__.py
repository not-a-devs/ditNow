from app.config import Settings
from app.llm.base import ChatMessage, LLMAuthError, LLMClient, LLMError

__all__ = ["ChatMessage", "LLMAuthError", "LLMClient", "LLMError", "get_llm_client"]


def get_llm_client(settings: Settings) -> LLMClient:
    """`.env`의 LLM_PROVIDER에 맞는 클라이언트를 만든다."""
    provider = settings.llm_provider
    if provider == "fake":
        from app.llm.fake_client import FakeLLMClient

        return FakeLLMClient()
    if not settings.llm_model:
        raise ValueError("LLM_MODEL이 비어 있습니다 (.env 확인)")
    if provider in ("openai", "openai_compatible"):
        from app.llm.openai_client import OpenAIClient

        base_url = None
        if provider == "openai_compatible":
            if not settings.llm_base_url:
                raise ValueError("openai_compatible은 LLM_BASE_URL이 필요합니다")
            base_url = settings.llm_base_url
        return OpenAIClient(
            settings.llm_model, settings.llm_api_key, settings.llm_timeout_sec, base_url
        )
    if provider == "anthropic":
        from app.llm.anthropic_client import AnthropicClient

        return AnthropicClient(settings.llm_model, settings.llm_api_key, settings.llm_timeout_sec)
    raise ValueError(f"알 수 없는 LLM_PROVIDER: {provider}")
