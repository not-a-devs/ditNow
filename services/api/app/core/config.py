from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DIT_API_", extra="ignore", hide_input_in_errors=True, env_file=None
    )

    environment: Literal["development", "test", "production"]
    log_level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = []
    docs_enabled: bool = False

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
