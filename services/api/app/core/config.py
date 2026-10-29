from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, FilePath, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DIT_API_", extra="ignore", hide_input_in_errors=True, env_file=None
    )

    environment: Literal["development", "test", "production"]
    log_level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = []
    docs_enabled: bool = False
    # Optional until operational access is approved; a partial configuration is invalid.
    db_host: str | None = Field(default=None, repr=False)
    db_port: int = Field(default=3307, ge=1, le=65535)
    db_name: Literal["ditnow"] = "ditnow"
    db_user: Literal["ditnow_app"] | None = None
    db_password: SecretStr | None = None
    db_tls_ca_file: FilePath | None = Field(default=None, repr=False)
    db_connect_timeout: int = Field(default=5, ge=1, le=5)

    @field_validator("db_host")
    @classmethod
    def validate_db_host(cls, value: str | None) -> str | None:
        if value is not None and (
            not value
            or not value.isascii()
            or any(c.isspace() for c in value)
            or any(c in value for c in "/\\@:#?[]")
        ):
            raise ValueError("DB host must be an explicit hostname or IPv4 address")
        return value

    @model_validator(mode="after")
    def validate_database_configuration(self) -> "Settings":
        present = [self.db_host is not None, self.db_user is not None, self.db_password is not None]
        any_database_setting = any(name.startswith("db_") for name in self.model_fields_set)
        if any_database_setting and not all(present):
            raise ValueError("DB host, app user and password must be configured together")
        if self.db_password is not None and not self.db_password.get_secret_value():
            raise ValueError("DB password must not be empty")
        if self.db_tls_ca_file is not None and not all(present):
            raise ValueError("DB TLS CA requires complete DB configuration")
        return self

    @property
    def database_configured(self) -> bool:
        return self.db_host is not None

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
