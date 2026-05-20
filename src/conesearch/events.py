"""App metrics events."""

from datetime import timedelta
from typing import override

from safir.dependencies.metrics import EventMaker
from safir.metrics import EventManager, EventPayload

__all__ = ["ConeSearchQueryFailed", "ConeSearchQuerySucceeded", "Events"]


class ConeSearchQuerySucceeded(EventPayload):
    """Reported when a ConeSearch query is successfully executed."""

    duration: timedelta
    tap_duration: timedelta
    username: str


class ConeSearchQueryFailed(EventPayload):
    """Reported when a ConeSearch query fails."""

    username: str
    duration: timedelta
    error: str | None = None


class Events(EventMaker):
    """Container for app metrics event publishers."""

    @override
    async def initialize(self, manager: EventManager) -> None:
        self.conesearch_query_succeeded = await manager.create_publisher(
            "conesearch_query_succeeded", ConeSearchQuerySucceeded
        )
        self.conesearch_query_failed = await manager.create_publisher(
            "conesearch_query_failed", ConeSearchQueryFailed
        )
