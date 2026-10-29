from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """`.env`에서 읽는 서버 설정."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", extra="ignore", hide_input_in_errors=True
    )

    data_dir: Path = ROOT_DIR / "data"
    mock_dir: Path = ROOT_DIR / "data" / "mock"  # DB 시드용 학생 목업

    # 예: mysql+aiomysql://ditnow:ditnow@localhost:3306/ditnow?charset=utf8mb4
    database_url: SecretStr = Field(default=SecretStr(""), repr=False)
    db_auto_init: bool = False  # 호환 키. 런타임 DDL/자동 시드는 허용하지 않는다.
    current_semester: str = "2026-2"

    llm_provider: str = "openai"
    llm_model: str = ""
    llm_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    llm_base_url: str = ""
    llm_timeout_sec: float = 20

    min_score: float = 0.35
    top_k: int = 5
    max_context_chars: int = 3000

    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    admin_token: SecretStr = Field(default=SecretStr(""), repr=False)
    rate_limit_per_min: int = 20

    @field_validator("db_auto_init")
    @classmethod
    def disallow_runtime_initialization(cls, value: bool) -> bool:
        """기존 환경의 true도 조용히 실행하지 않고 안전하게 거부한다."""
        if value:
            raise ValueError("DB_AUTO_INIT은 false여야 합니다. 스키마 변경은 별도 승인 작업입니다.")
        return value


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 한 번만 만들어 재사용한다."""
    return Settings()
