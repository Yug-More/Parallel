"""Parallel's HTTP composition root. Schema changes run through Alembic only."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from api import auth, messages, workspaces
from config import load_settings
from database import create_db_engine

SCHEMA_REVISION = "0002_workspaces"


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def request_safety(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and origin not in settings.allowed_origins) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return JSONResponse({"detail": "Request origin not allowed"}, status_code=403)
        response = await call_next(request)
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

    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(messages.router)

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
