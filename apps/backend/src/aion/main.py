from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import Response

from aion.auth import AuthError, AuthService, router
from aion.config import Settings
from aion.database import is_ready, make_engine
from aion.profiles import router as profile_router


class Health(BaseModel):
    status: Literal["ok", "unavailable"]


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configured = settings or Settings()
        engine = make_engine(configured)
        app.state.engine = engine
        try:
            app.state.auth = AuthService(engine, configured) if configured.auth_enabled else None
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Aion API — foundation",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )

    @app.middleware("http")
    async def private_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": codes.get(exc.status_code, "request_failed")}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request"}})

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code}},
            headers={"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": {"code": "unavailable"}})

    app.include_router(router)
    app.include_router(profile_router)

    @app.get("/api/v1/health/live", response_model=Health)
    def live() -> Health:
        return Health(status="ok")

    @app.get(
        "/api/v1/health/ready",
        response_model=Health,
        responses={503: {"model": Health}},
    )
    def ready(request: Request) -> JSONResponse:
        available = is_ready(request.app.state.engine)
        return JSONResponse(
            status_code=200 if available else 503,
            content={"status": "ok" if available else "unavailable"},
        )

    return app
