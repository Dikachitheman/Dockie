"""
FastAPI application factory.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.application.adk_agent import build_adk_agent, diagnose_adk_database_schema
from app.infrastructure.cache import check_cache_connection
from app.infrastructure.database import check_database_connection
from app.interfaces.api.routes.agent_run import router as agent_run_router
from app.interfaces.api.routes.geo import router as geo_router
from app.interfaces.api.routes.meta import agent_router, router as meta_router
from app.interfaces.api.routes.shipments import router as shipments_router
from app.interfaces.api.routes.standby import router as standby_router

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    logger.info("dockie_copilot_startup", env=settings.app_env)
    try:
        await check_database_connection()
        logger.info("database_connection_status", status="connected")
    except Exception as exc:
        logger.error("database_connection_status", status="failed", error=str(exc))
        raise
    cache_connected = await check_cache_connection()
    logger.info("cache_connection_status", status="connected" if cache_connected else "disabled_or_unavailable")
    logger.info(
        "agent_audit_log_status",
        enabled=settings.agent_audit_log_enabled,
        path=settings.agent_audit_log_path,
    )
    diagnose_adk_database_schema()
    app.state.adk_agent = build_adk_agent()
    yield
    logger.info("dockie_copilot_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dockie Copilot API",
        description="Shipment tracking copilot for ro-ro vessels on the US–West Africa corridor.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global error handler — never leak stack traces to clients
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", path=str(request.url), error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": "An unexpected error occurred."},
        )

    app.include_router(meta_router)
    app.include_router(agent_router)
    app.include_router(agent_run_router)
    app.include_router(shipments_router)
    app.include_router(geo_router)
    app.include_router(standby_router)

    return app
