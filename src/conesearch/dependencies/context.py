"""Request context dependency for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from httpx import AsyncClient
from safir.dependencies.gafaelfawr import (
    auth_delegated_token_dependency,
    auth_dependency,
)
from safir.dependencies.http_client import http_client_dependency
from safir.dependencies.logger import logger_dependency
from safir.metrics import EventManager
from structlog.stdlib import BoundLogger

from ..config import Config
from ..events import Events
from ..factory import Factory

__all__ = ["ContextDependency", "RequestContext", "context_dependency"]


@dataclass(slots=True)
class RequestContext:
    """Holds the incoming request and its surrounding context."""

    request: Request
    """The incoming request."""

    config: Config
    """ConeSearch configuration."""

    logger: BoundLogger
    """The request logger."""

    factory: Factory
    """The component factory."""


class ContextDependency:
    """Provide a per-request context as a FastAPI dependency.

    Process-wide state (config and event publishers) is held on the instance
    and shared across all requests.  Per-request state (auth token, username,
    HTTP client, logger) is gathered on each call via FastAPI dependencies.
    """

    def __init__(self) -> None:
        self._config: Config | None = None
        self._events: Events | None = None

    async def __call__(
        self,
        *,
        request: Request,
        http_client: Annotated[AsyncClient, Depends(http_client_dependency)],
        delegated_token: Annotated[
            str, Depends(auth_delegated_token_dependency)
        ],
        logger: Annotated[BoundLogger, Depends(logger_dependency)],
        username: Annotated[str, Depends(auth_dependency)],
    ) -> RequestContext:
        """Create a per-request context.

        Raises
        ------
        RuntimeError
            If called before `initialize`.
        """
        if self._config is None or self._events is None:
            raise RuntimeError("ContextDependency not initialized")
        factory = Factory(
            http_client=http_client,
            delegated_token=delegated_token,
            logger=logger,
            events=self._events,
            username=username,
        )
        return RequestContext(
            request=request,
            config=self._config,
            logger=logger,
            factory=factory,
        )

    async def initialize(
        self, config: Config, event_manager: EventManager
    ) -> None:
        """Initialize the process-wide shared context.

        Parameters
        ----------
        config
            ConeSearch configuration.
        event_manager
            Global event manager used to create event publishers.
        """
        self._config = config
        self._events = Events()
        await self._events.initialize(event_manager)

    async def aclose(self) -> None:
        """Clean up the process-wide context."""
        self._events = None
        self._config = None


context_dependency = ContextDependency()
"""The dependency that will return the per-request context."""
