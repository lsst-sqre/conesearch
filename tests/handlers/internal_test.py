"""Tests for the conesearch.handlers.internal module and routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from conesearch.dependencies.config import config_dependency


@pytest.mark.asyncio
async def test_get_index(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == config_dependency.config().name
    assert isinstance(data["version"], str)
    assert isinstance(data["description"], str)
    assert isinstance(data["repository_url"], str)
    assert isinstance(data["documentation_url"], str)
