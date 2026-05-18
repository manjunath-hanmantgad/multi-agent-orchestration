"""FastAPI gateway for workflow orchestration and review APIs."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from api.dependencies import get_registry
from api.routers import approvals, audit, workflows

DEFAULT_CHECKPOINT_DB_URL = "./checkpoints.db"
_checkpoint_ctx: Any | None = None
_checkpoint_saver: AsyncSqliteSaver | None = None


def _error_payload(message: str) -> dict[str, Any]:
    return {"success": False, "data": None, "error": message}


def _configure_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_routes(app: FastAPI) -> None:
    app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
    app.include_router(approvals.router, prefix="/api/workflows", tags=["approvals"])
    app.include_router(audit.router, prefix="/api/workflows", tags=["audit"])


def _register_lifecycle(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        registry = get_registry()
        await _ensure_checkpoint_saver()
        _inject_checkpoint_saver(registry, _checkpoint_saver)
        _ = registry.list_workflows()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await _close_checkpoint_saver()
        return None


def _register_health(app: FastAPI) -> None:
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        registry = get_registry()
        return {
            "success": True,
            "data": {"status": "ok", "workflows_registered": len(registry.list_workflows())},
            "error": None,
        }


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_payload(str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        _ = exc
        return JSONResponse(
            status_code=400,
            content={"success": False, "data": None, "error": "Invalid request payload"},
        )

    @app.exception_handler(Exception)
    async def _unexpected_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=_error_payload(str(exc)))


def create_app() -> FastAPI:
    """Build FastAPI application with routers and uniform error handling."""
    app = FastAPI(title="Enterprise Agentic Workflow Platform API", version="0.1.0")
    _configure_cors(app)
    _register_routes(app)
    _register_lifecycle(app)
    _register_health(app)
    _register_exception_handlers(app)
    return app


app = create_app()


def _checkpoint_db_url() -> str:
    value = os.getenv("CHECKPOINT_DB_URL", DEFAULT_CHECKPOINT_DB_URL).strip()
    return value or DEFAULT_CHECKPOINT_DB_URL


async def _ensure_checkpoint_saver() -> AsyncSqliteSaver:
    global _checkpoint_ctx, _checkpoint_saver
    if _checkpoint_saver is None:
        _checkpoint_ctx = AsyncSqliteSaver.from_conn_string(_checkpoint_db_url())
        _checkpoint_saver = await _checkpoint_ctx.__aenter__()
        await _checkpoint_saver.setup()
    return _checkpoint_saver


def _inject_checkpoint_saver(registry: Any, checkpointer: AsyncSqliteSaver | None) -> None:
    if checkpointer is None:
        return
    for item in registry.list_workflows():
        workflow = registry.get(item["name"])
        if hasattr(workflow, "_checkpointer"):
            setattr(workflow, "_checkpointer", checkpointer)
        if hasattr(workflow, "_compiled_graph"):
            setattr(workflow, "_compiled_graph", None)


async def _close_checkpoint_saver() -> None:
    global _checkpoint_ctx, _checkpoint_saver
    if _checkpoint_ctx is not None:
        await _checkpoint_ctx.__aexit__(None, None, None)
    _checkpoint_ctx = None
    _checkpoint_saver = None
