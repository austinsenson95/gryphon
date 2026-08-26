"""Griffin backend application factory.

Wires CORS, routers, structured error envelopes, and the lifespan that builds
the database, tool registry, LLM provider, WebSocket manager and event bus.
Boots with zero external credentials (mock LLM + mock web/browser tools).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import browser, chat, events, health, llm, phone, remote, tasks, voice, websocket
from backend.core.config import APP_VERSION, Settings, get_settings
from backend.core.logging import get_logger, setup_logging
from backend.core.state import AppState
from backend.memory import retrieval as repository
from backend.memory.database import Database
from backend.events.bus import EventBus
from backend.events.events import envelope_from_row
from backend.events.websocket_manager import WebSocketManager
from backend.llm.ollama import OllamaProvider
from backend.llm.provider import get_llm_provider
from backend.stt.local import get_stt_provider
from backend.tools.registry import create_default_registry
from backend.remote.service import RemoteControlService
from backend.phone.service import PhoneService

logger = get_logger("griffin.main")

# CORS: explicit dev origins plus LAN origin patterns (dev convenience).
LAN_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.async_database_url)
        await db.create_tables()

        async def recent_events(limit: int):
            async with db.session_factory() as session:
                rows = await repository.get_recent_events(session, limit=limit)
            return [envelope_from_row(row) for row in rows]

        ws_manager = WebSocketManager(history_provider=recent_events)
        bus = EventBus(db.session_factory, ws_manager)

        phone_service = PhoneService(settings, db.session_factory, bus)
        await phone_service.seed_contacts()

        # Registry is built with shared services so tools can stream progress events.
        registry = create_default_registry(settings, bus=bus, phone_service=phone_service)
        provider = get_llm_provider(settings)
        stt = get_stt_provider(settings)

        app.state.griffin = AppState(
            settings=settings,
            db=db,
            registry=registry,
            provider=provider,
            bus=bus,
            ws_manager=ws_manager,
            stt=stt,
            remote=RemoteControlService(),
            phone=phone_service,
        )

        # Startup verification for Ollama: report clearly instead of failing
        # silently later (the app still boots so /api/health/ollama can diagnose).
        if isinstance(provider, OllamaProvider):
            ollama_health = await provider.health_check()
            if ollama_health["reachable"] and ollama_health["model_available"] and ollama_health["inference_ok"]:
                logger.info("llm.ollama.healthy", extra={"model": ollama_health["model"]})
            else:
                logger.warning(
                    "llm.ollama.unhealthy",
                    extra={"detail": {k: v for k, v in ollama_health.items() if k != "installed_models"}},
                )

        logger.info(
            "app.started",
            extra={
                "app": settings.app_name,
                "version": APP_VERSION,
                "environment": settings.environment,
                "llm_mode": settings.llm_mode,
                "tools": [t.name for t in registry.list()],
            },
        )
        try:
            yield
        finally:
            browser_manager = getattr(registry, "browser", None)
            if browser_manager is not None:
                await browser_manager.close()
            await db.dispose()
            logger.info("app.stopped")

    app = FastAPI(title=settings.app_name, version=APP_VERSION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=LAN_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = _error_body(exc.detail["code"], exc.detail.get("message", ""))
        else:
            body = _error_body("HTTP_ERROR", str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", []))
        message = f"{location}: {first.get('msg', 'invalid request')}"
        return JSONResponse(
            status_code=422, content=_error_body("VALIDATION_ERROR", message)
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("app.unhandled_error")
        return JSONResponse(
            status_code=500, content=_error_body("INTERNAL_ERROR", "Internal server error")
        )

    app.include_router(health.router)
    app.include_router(llm.router)
    app.include_router(browser.router)
    app.include_router(chat.router)
    app.include_router(voice.router)
    app.include_router(tasks.router)
    app.include_router(events.router)
    app.include_router(remote.router)
    app.include_router(phone.router)
    app.include_router(websocket.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
