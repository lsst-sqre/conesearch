"""The main application factory for the conesearch service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import metadata, version

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from rubin.repertoire import DiscoveryClient
from safir.dependencies.http_client import http_client_dependency
from safir.middleware.ivoa import CaseInsensitiveQueryMiddleware
from safir.middleware.x_forwarded import XForwardedMiddleware
from safir.slack.webhook import SlackRouteErrorHandler

from .config import Config
from .dependencies.config import config_dependency
from .dependencies.context import context_dependency
from .handlers.external import external_router
from .handlers.internal import internal_router
from .services.votable import votable_error

__all__ = ["create_app"]


async def _validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> Response:
    """Convert FastAPI validation errors to VOTable error responses.

    The ConeSearch standard requires that invalid parameter errors be
    reported as ``QUERY_STATUS=ERROR`` inside a VOTable response, rather
    than the HTTP 422 that FastAPI would normally return. Per DALI 1.1
    section 4.2, errors in the use of the protocol (such as a missing or
    unparseable RA, DEC, or SR) are a client-request problem and must be
    reported with a 4xx status code, so HTTP 400 is used instead of 422
    or the 200 used for errors detected only after a query has already
    started streaming.
    """
    message = "; ".join(
        f"{e['loc'][-1] if e['loc'] else 'request'}: {e['msg']}"
        for e in exc.errors()
    )
    return Response(
        content=votable_error(message),
        media_type="application/x-votable+xml",
        status_code=400,
    )


async def _resolve_tap_urls(config: Config) -> None:
    """Resolve TAP base URLs for all collections via Repertoire at startup."""
    discovery = DiscoveryClient()
    try:
        for name, collection in config.collections.items():
            tap_base = await discovery.url_for_data("tap", name)
            if tap_base is None:
                raise RuntimeError(
                    f"Repertoire returned no TAP service for dataset {name!r}"
                )
            collection._tap_url = tap_base  # noqa: SLF001
    finally:
        await discovery.aclose()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    config = config_dependency.config()

    if config.slack_webhook:
        logger = structlog.get_logger("conesearch")
        SlackRouteErrorHandler.initialize(
            config.slack_webhook, "conesearch", logger
        )
        logger.debug("Initialized Slack webhook")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        await _resolve_tap_urls(config)
        event_manager = config.metrics.make_manager()
        await event_manager.initialize()
        await context_dependency.initialize(config, event_manager)
        yield
        await context_dependency.aclose()
        await event_manager.aclose()
        await http_client_dependency.aclose()

    app = FastAPI(
        title="conesearch",
        description=metadata("conesearch")["Summary"],
        version=version("conesearch"),
        openapi_url=f"{config.path_prefix}/openapi.json",
        docs_url=f"{config.path_prefix}/docs",
        redoc_url=f"{config.path_prefix}/redoc",
        lifespan=lifespan,
    )

    app.include_router(internal_router)
    app.include_router(external_router, prefix=config.path_prefix)
    app.add_middleware(XForwardedMiddleware)
    app.add_middleware(CaseInsensitiveQueryMiddleware)
    app.add_exception_handler(
        RequestValidationError,
        _validation_exception_handler,  # type: ignore[arg-type]
    )

    return app


app = create_app()
"""The main FastAPI application for conesearch."""
