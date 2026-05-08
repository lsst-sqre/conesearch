"""Test fixtures for conesearch tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from conesearch.config import CollectionConfig, Config
from conesearch.dependencies.config import config_dependency
from conesearch.services.conesearch import ConeSearchService
from tests.support.mocks import make_collection, make_service

_TEST_CONFIG = Path(__file__).parent / "data" / "config" / "test.yaml"
_TEST_TAP_URL = "https://tap.example.com/api/tap"


async def _mock_resolve_tap_urls(config: Config) -> None:
    for collection in config.collections.values():
        collection._tap_url = _TEST_TAP_URL


@pytest_asyncio.fixture
async def app() -> AsyncGenerator[FastAPI]:
    """Return a configured test application."""
    config_dependency.set_config_path(_TEST_CONFIG)
    from conesearch.main import create_app  # noqa: PLC0415

    app = create_app()
    with patch("conesearch.main._resolve_tap_urls", _mock_resolve_tap_urls):
        async with LifespanManager(app):
            yield app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Return an httpx.AsyncClient configured to talk to the test app."""
    async with AsyncClient(
        base_url="https://example.com/",
        headers={
            "X-Auth-Request-User": "test-user",
            "X-Auth-Request-Token": "gt-test-token",
        },
        transport=ASGITransport(app=app),
    ) as client:
        yield client


@pytest.fixture
def collection() -> CollectionConfig:
    """Return a test CollectionConfig."""
    return make_collection()


@pytest.fixture
def service() -> ConeSearchService:
    """Return a ConeSearchService wired to mock dependencies."""
    return make_service()
