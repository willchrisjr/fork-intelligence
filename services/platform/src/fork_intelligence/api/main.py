from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from time import time
from typing import cast

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from starlette.responses import Response

from fork_intelligence import __version__
from fork_intelligence.api.routes import router
from fork_intelligence.config import get_settings
from fork_intelligence.errors import PlatformError
from fork_intelligence.schemas import ProblemDetails

logger = structlog.get_logger()
settings = get_settings()
app = FastAPI(
    title="Fork Intelligence Platform API",
    version=__version__,
    description="Evidence-backed, progressively persisted GitHub fork analysis.",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    responses={
        422: {"model": ProblemDetails, "description": "Request validation failed"},
        500: {"model": ProblemDetails, "description": "Safe internal error"},
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID", "X-Request-ID"],
)
app.include_router(router)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    if request.method == "POST" and request.url.path == "/api/v1/analyses":
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdecimal()
            and int(content_length) > settings.max_request_body_bytes
        ):
            return _middleware_problem(
                request, request_id, "request_too_large", 413, "Request body exceeds its limit"
            )
        body = await request.body()
        if len(body) > settings.max_request_body_bytes:
            return _middleware_problem(
                request, request_id, "request_too_large", 413, "Request body exceeds its limit"
            )
        client_host = request.client.host if request.client else "unknown"
        try:
            redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
            bucket = int(time() // 60)
            key = f"fork-intelligence:admission:{client_host}:{bucket}"
            count = cast(int, redis.incr(key))
            if count == 1:
                redis.expire(key, 120)
            redis.close()
            if count > settings.analysis_requests_per_minute:
                return _middleware_problem(
                    request,
                    request_id,
                    "analysis_rate_limited",
                    429,
                    "Too many analysis requests; retry after the current minute",
                )
        except Exception as exc:
            # PostgreSQL queue admission below remains authoritative if Redis is unavailable.
            logger.warning("admission_redis_unavailable", error_type=type(exc).__name__)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _middleware_problem(
    request: Request, request_id: str, code: str, status_code: int, detail: str
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://fork-intelligence.local/problems/{code}",
            "title": code.replace("_", " ").title(),
            "status": status_code,
            "detail": detail,
            "instance": request.url.path,
            "code": code,
            "details": {},
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(PlatformError)
async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
    logger.info("platform_error", code=exc.code, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://fork-intelligence.local/problems/{exc.code}",
            "title": exc.code.replace("_", " ").title(),
            "status": exc.status_code,
            "detail": exc.message,
            "instance": request.url.path,
            "code": exc.code,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content=jsonable_encoder(
            {
                "type": "https://fork-intelligence.local/problems/validation_error",
                "title": "Validation Error",
                "status": 422,
                "detail": "Request validation failed",
                "instance": request.url.path,
                "code": "validation_error",
                "details": {"errors": exc.errors()},
                "request_id": getattr(request.state, "request_id", None),
            }
        ),
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        media_type="application/problem+json",
        content={
            "type": "https://fork-intelligence.local/problems/internal_error",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected server error occurred",
            "instance": request.url.path,
            "code": "internal_error",
            "details": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def run() -> None:
    uvicorn.run(
        "fork_intelligence.api.main:app",
        host="0.0.0.0",  # noqa: S104 - container entrypoint must listen beyond loopback.
        port=8000,
        reload=False,
        proxy_headers=True,
    )
