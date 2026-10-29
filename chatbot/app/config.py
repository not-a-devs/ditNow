from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """`.env`에서 읽는 서버 설정."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    data_dir: Path = ROOT_DIR / "data"

    llm_provider: str = "openai"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_sec: float = 20

    min_score: float = 0.35
    top_k: int = 5
    max_context_chars: int = 3000

    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    admin_token: str = ""
    rate_limit_per_min: int = 20


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 한 번만 만들어 재사용한다."""
    return Settings()
