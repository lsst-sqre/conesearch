"""Component factory for conesearch."""

from __future__ import annotations

import httpx
from structlog.stdlib import BoundLogger

from .events import Events
from .services.conesearch import ConeSearchService

__all__ = ["Factory"]


class Factory:
    """Component factory for conesearch.

    Holds the per-request dependencies and creates service instances on
    demand.

    Parameters
    ----------
    http_client
        Shared async HTTP client used for TAP sync requests.
    delegated_token
        Gafaelfawr delegated token passed as a Bearer credential to TAP.
    logger
        Bound logger for structured log output.
    events
        Metrics event publishers.
    username
        Authenticated username.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        delegated_token: str,
        logger: BoundLogger,
        events: Events,
        username: str,
    ) -> None:
        self._http_client = http_client
        self._delegated_token = delegated_token
        self._logger = logger
        self._events = events
        self._username = username

    def create_conesearch_service(self) -> ConeSearchService:
        """Create a `ConeSearchService` for the current request.

        Returns
        -------
        ConeSearchService
            A configured service instance.
        """
        return ConeSearchService(
            http_client=self._http_client,
            delegated_token=self._delegated_token,
            logger=self._logger,
            events=self._events,
            username=self._username,
        )
