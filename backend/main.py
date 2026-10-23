"""Parallel's HTTP composition root. Schema changes run through Alembic only."""

import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from api import (
    actions,
    agents,
    answers,
    auth,
    decisions,
    documents,
    github_app,
    intelligence,
    invitations,
    messages,
    overview,
    repositories,
    semantic,
    tasks,
    workspaces,
)
from config import load_settings
from database import create_db_engine
from rate_limit import SharedRateLimiter
from request_limits import RequestBodyLimit

SCHEMA_REVISION = "0013_shared_limits"
logger = logging.getLogger("parallel.http")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())


def create_app(settings=None):
    settings = settings or load_settings()
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        try:
            with engine.connect() as connection:
                if (
                    "alembic_version" not in inspect(connection).get_table_names()
                    or connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                    != SCHEMA_REVISION
                ):
                    raise RuntimeError(
                        "Database migration required: run python migrate.py before starting"
                    )
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Parallel", version="2.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.auth_limiter = SharedRateLimiter(app.state.session_factory, settings.secret_key)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    app.add_middleware(RequestBodyLimit)

    @app.middleware("http")
    async def request_safety(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and origin not in settings.allowed_origins) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return JSONResponse({"detail": "Request origin not allowed"}, status_code=403)
        request_id, started = str(uuid4()), time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(
                {"detail": "Request failed", "request_id": request_id}, status_code=500
            )
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "route": getattr(route, "path", "unmatched"),
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        return JSONResponse(
            {
                "detail": [
                    {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        try:
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
            if revision != SCHEMA_REVISION:
                return JSONResponse({"status": "not_ready"}, status_code=503)
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return {"status": "ready"}

    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(messages.router)
    app.include_router(invitations.router)
    app.include_router(tasks.router)
    app.include_router(agents.router)
    app.include_router(decisions.router)
    app.include_router(intelligence.router)
    app.include_router(actions.router)
    app.include_router(overview.router)
    app.include_router(answers.router)
    app.include_router(documents.router)
    app.include_router(repositories.router)
    app.include_router(semantic.router)
    app.include_router(github_app.router)

    @app.websocket("/voice/ws")
    async def disabled_voice(websocket: WebSocket):
        await websocket.close(code=1008, reason="Voice is disabled")

    @app.api_route("/{legacy_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unsupported(legacy_path: str):
        unsafe = {
            "voice",
            "sms",
            "plivo",
            "composio",
            "summary",
            "chat",
            "messages",
            "activity",
            "online",
            "tools",
            "tunnel",
            "events",
            "rooms",
            "tasks",
        }
        if legacy_path.split("/", 1)[0] in unsafe:
            return JSONResponse(
                {
                    "detail": "Legacy endpoint disabled. Use workspace-scoped APIs; external tools are unavailable."
                },
                status_code=410,
            )
        return JSONResponse({"detail": "Not found"}, status_code=404)

    return app


app = create_app()
