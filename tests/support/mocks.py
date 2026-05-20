"""Mock helpers for conesearch tests."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
from structlog.stdlib import BoundLogger

from conesearch.config import CollectionConfig
from conesearch.events import Events
from conesearch.services.conesearch import ConeSearchService

__all__ = ["make_collection", "make_service"]


def make_collection(**overrides: Any) -> CollectionConfig:
    """Build a `CollectionConfig`.

    Parameters
    ----------
    **overrides
        Fields to override in the default config (camelCase keys).

    Returns
    -------
    CollectionConfig
        A validated collection config.
    """
    data: dict[str, Any] = {
        "table": "test.Object",
        "idColumn": "objectId",
        "raColumn": "coord_ra",
        "decColumn": "coord_dec",
        "maxRecords": 100,
        "verb1Columns": ["objectId", "coord_ra", "coord_dec"],
        "verb2Columns": ["objectId", "coord_ra", "coord_dec", "flux"],
    }
    data.update(overrides)
    collection = CollectionConfig.model_validate(data)
    collection._tap_url = "https://tap.example.com/api/tap"
    return collection


def make_service() -> ConeSearchService:
    """Build a `ConeSearchService` with mock dependencies.

    Returns
    -------
    ConeSearchService
        A service wired to a mock HTTP client and event publishers.
    """
    events = cast("Events", MagicMock(spec=Events))
    events.conesearch_query_succeeded = MagicMock()
    events.conesearch_query_succeeded.publish = AsyncMock()
    events.conesearch_query_failed = MagicMock()
    events.conesearch_query_failed.publish = AsyncMock()
    return ConeSearchService(
        http_client=httpx.AsyncClient(),
        delegated_token="test-token",
        logger=cast("BoundLogger", MagicMock()),
        events=events,
        username="test-user",
    )
