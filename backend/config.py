"""Validated configuration, loaded before database construction."""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

_DEV_SECRET = secrets.token_urlsafe(48)


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    environment: str = "development"
    allowed_origins: tuple[str, ...] = ("http://localhost:5174", "http://127.0.0.1:5174")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    def __post_init__(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if len(self.secret_key.encode()) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 bytes")
        if not self.database_url.startswith(("sqlite:", "postgresql")):
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL")
        if not self.allowed_origins or "*" in self.allowed_origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins")
        if self.environment == "production" and any(
            not origin.startswith("https://") for origin in self.allowed_origins
        ):
            raise ValueError("Production CORS_ORIGINS must use HTTPS")

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    if environ is None:
        load_dotenv(Path(__file__).with_name(".env"))
        environ = os.environ
    environment = environ.get("APP_ENV", "development")
    secret = environ.get("SECRET_KEY")
    if not secret and environment == "production":
        raise ValueError("SECRET_KEY is required in production")
    return Settings(
        database_url=environ.get("DATABASE_URL", "sqlite:///./parallel.db"),
        secret_key=secret or _DEV_SECRET,
        environment=environment,
        allowed_origins=tuple(
            origin.strip().rstrip("/")
            for origin in environ.get(
                "CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174"
            ).split(",")
            if origin.strip()
        ),
        openai_api_key=environ.get("OPENAI_API_KEY") or None,
        openai_model=environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
    )
