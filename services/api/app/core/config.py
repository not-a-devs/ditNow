from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DIT_API_", extra="ignore", hide_input_in_errors=True, env_file=None
    )

    environment: Literal["development", "test", "production"]
    log_level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = []
    docs_enabled: bool = False

    # 학번 로그인·개인 질문용 학적 DB. 비어 있으면 로그인과 개인 질문이 503
    # 예: mysql+aiomysql://ditnow_app:<pw>@<tailscale-ip>:3307/ditnow?charset=utf8mb4
    database_url: SecretStr | None = None
    current_semester: str = "2026-2"
    # AI 답변 생성. 비어 있으면 /ai/ask가 503 (공개 검색 /ai/campus/search는 LLM 없이 동작)
    llm_provider: Literal["openai", "openai_compatible", "anthropic", "fake"] | None = None
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_timeout_sec: float = 20
    ask_rate_limit_per_min: int = 20

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or not origin.isascii()
                or any(character.isspace() for character in origin)
            ):
                raise ValueError("CORS requires explicit HTTP origins without paths or credentials")
            try:
                _ = parsed.port
            except ValueError:
                raise ValueError("CORS origin port is invalid") from None
        return list(dict.fromkeys(origins))
