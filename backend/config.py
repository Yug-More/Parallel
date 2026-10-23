"""Validated configuration, loaded before database construction."""

import os
import re
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
    github_app_enabled: bool = False
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None
    github_app_id: int | None = None
    credential_encryption_key: str | None = None
    embedding_provider: str = "disabled"
    embedding_model: str = "text-embedding-3-small"
    embedding_revision: str = "v1"
    embedding_dimensions: int = 384
    embedding_local_path: str | None = None
    embedding_artifact_sha256: str | None = None
    external_embeddings_enabled: bool = False
    recovery_outbox_path: str | None = None
    local_index_enabled: bool = False
    grounded_model_enabled: bool = False
    github_connector_enabled: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    def __post_init__(self):
        if self.embedding_provider not in {"disabled", "local", "openai"}:
            raise ValueError("EMBEDDING_PROVIDER must be disabled, local or openai")
        if not 1 <= self.embedding_dimensions <= 1536:
            raise ValueError("EMBEDDING_DIMENSIONS must be between 1 and 1536")
        if not re.fullmatch(r"[A-Za-z0-9_./:-]{1,80}", self.embedding_model):
            raise ValueError("EMBEDDING_MODEL must be a bounded model identifier")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", self.embedding_revision):
            raise ValueError("EMBEDDING_REVISION must be bounded and explicit")
        if self.embedding_provider == "local" and not (
            self.embedding_local_path
            and self.embedding_artifact_sha256
            and re.fullmatch(r"[a-f0-9]{64}", self.embedding_artifact_sha256)
        ):
            raise ValueError(
                "Local embeddings require an operator-provisioned path and artifact SHA256"
            )
        if self.embedding_provider == "openai" and not (
            self.external_embeddings_enabled and self.openai_api_key
        ):
            raise ValueError("External embeddings require explicit enablement and a server key")

        if self.recovery_outbox_path and (
            self.environment == "production" or not Path(self.recovery_outbox_path).is_absolute()
        ):
            raise ValueError("Local recovery outbox requires an absolute path in development/test")
        if self.github_app_enabled:
            if not all(
                (
                    self.github_connector_enabled,
                    self.github_app_client_id,
                    self.github_app_client_secret,
                    self.github_app_id,
                    self.credential_encryption_key,
                )
            ):
                raise ValueError(
                    "GitHub App requires connector opt-in, app/client IDs, client secret and separate encryption key"
                )
            from cryptography.fernet import Fernet

            try:
                Fernet(self.credential_encryption_key.encode())
            except Exception:
                raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be a Fernet key") from None

        if (
            not self.openai_model
            or len(self.openai_model) > 200
            or any(c.isspace() for c in self.openai_model)
        ):
            raise ValueError("OPENAI_MODEL must be a bounded model identifier")
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
        github_app_enabled=environ.get("GITHUB_APP_ENABLED", "false").lower() == "true",
        github_app_client_id=environ.get("GITHUB_APP_CLIENT_ID") or None,
        github_app_client_secret=environ.get("GITHUB_APP_CLIENT_SECRET") or None,
        github_app_id=int(environ["GITHUB_APP_ID"]) if environ.get("GITHUB_APP_ID") else None,
        credential_encryption_key=environ.get("CREDENTIAL_ENCRYPTION_KEY") or None,
        embedding_provider=environ.get("EMBEDDING_PROVIDER", "disabled"),
        embedding_model=environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_revision=environ.get("EMBEDDING_REVISION", "v1"),
        embedding_dimensions=int(environ.get("EMBEDDING_DIMENSIONS", "384")),
        embedding_local_path=environ.get("EMBEDDING_LOCAL_PATH") or None,
        embedding_artifact_sha256=environ.get("EMBEDDING_ARTIFACT_SHA256") or None,
        external_embeddings_enabled=environ.get("EXTERNAL_EMBEDDINGS_ENABLED", "false").lower()
        == "true",
        recovery_outbox_path=environ.get("RECOVERY_OUTBOX_PATH") or None,
        local_index_enabled=environ.get("LOCAL_INDEX_ENABLED", "false").lower() == "true",
        grounded_model_enabled=environ.get("GROUNDED_MODEL_ENABLED", "false").lower() == "true",
        github_connector_enabled=environ.get("GITHUB_CONNECTOR_ENABLED", "false").lower() == "true",
        openai_api_key=environ.get("OPENAI_API_KEY") or None,
        openai_model=environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
    )
