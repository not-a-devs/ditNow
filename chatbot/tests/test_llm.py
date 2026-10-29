import pytest

from app.config import Settings
from app.llm import ChatMessage, get_llm_client
from app.llm.anthropic_client import AnthropicClient
from app.llm.fake_client import FakeLLMClient
from app.llm.openai_client import OpenAIClient


def _settings(**kw: str) -> Settings:
    """.env를 읽지 않는 테스트용 설정."""
    return Settings(_env_file=None, llm_api_key="test", **kw)


@pytest.mark.parametrize(
    ("kw", "cls"),
    [
        ({"llm_provider": "fake"}, FakeLLMClient),
        ({"llm_provider": "openai", "llm_model": "m"}, OpenAIClient),
        ({"llm_provider": "anthropic", "llm_model": "m"}, AnthropicClient),
        (
            {"llm_provider": "openai_compatible", "llm_model": "m", "llm_base_url": "http://x"},
            OpenAIClient,
        ),
    ],
)
def test_factory(kw: dict[str, str], cls: type) -> None:
    """공급자 설정에 맞는 클라이언트를 만든다."""
    assert isinstance(get_llm_client(_settings(**kw)), cls)


@pytest.mark.parametrize(
    "kw",
    [
        {"llm_provider": "openai"},  # 모델 없음
        {"llm_provider": "openai_compatible", "llm_model": "m"},  # base_url 없음
        {"llm_provider": "nope", "llm_model": "m"},
    ],
)
def test_factory_rejects_bad_config(kw: dict[str, str]) -> None:
    """설정이 잘못되면 시작 시점에 에러."""
    with pytest.raises(ValueError):
        get_llm_client(_settings(**kw))


async def test_fake_client_echoes_context_ids() -> None:
    """가짜 클라이언트는 컨텍스트 id를 근거로 돌려준다."""
    msg = ChatMessage(role="user", content="<context>\n[a_1] 가\n- x\n[b_2] 나\n</context>")
    answer = await FakeLLMClient().chat([msg])
    assert answer.endswith("[근거: a_1, b_2]")


def test_openai_compatible_without_key() -> None:
    """키 없는 자체 서버도 클라이언트를 만들 수 있다."""
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_model="m",
        llm_base_url="http://10.0.0.1:8000/v1",
    )
    assert str(get_llm_client(settings).client.base_url).startswith("http://10.0.0.1:8000/v1")
