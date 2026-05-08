"""Tests for the conesearch.handlers.external module and routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from httpx import AsyncClient

from conesearch.dependencies.config import config_dependency

_TAP_VOTABLE = (
    Path(__file__).parent.parent / "data" / "votable" / "response.xml"
).read_bytes()

_TAP_SYNC_URL = "https://tap.example.com/api/tap/sync"


@pytest.mark.asyncio
async def test_get_index(client: AsyncClient) -> None:
    response = await client.get("/api/conesearch/")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metadata"]["name"] == config_dependency.config().name
    assert isinstance(data["metadata"]["version"], str)


@pytest.mark.asyncio
async def test_get_availability(client: AsyncClient) -> None:
    response = await client.get("/api/conesearch/test/availability")
    assert response.status_code == 200, response.text
    assert "application/xml" in response.headers["content-type"]
    assert b"<available>true</available>" in response.content


@pytest.mark.asyncio
async def test_get_capabilities(client: AsyncClient) -> None:
    response = await client.get("/api/conesearch/test/capabilities")
    assert response.status_code == 200, response.text
    assert "application/xml" in response.headers["content-type"]
    assert b"ConeSearch" in response.content
    assert b"capabilities" in response.content
    assert b"availability" in response.content
    assert b"<maxSR>10.0</maxSR>" in response.content
    assert b"<maxRecords>100</maxRecords>" in response.content
    assert b"<verbosity>true</verbosity>" in response.content


@pytest.mark.asyncio
async def test_get_capabilities_unknown_collection(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/conesearch/unknown/capabilities")
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_query(client: AsyncClient, respx_mock: respx.Router) -> None:
    respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1"},
    )
    assert response.status_code == 200, response.text
    assert "application/x-votable+xml" in response.headers["content-type"]
    assert b"ID_MAIN" in response.content
    assert b"POS_EQ_RA_MAIN" in response.content
    assert b"POS_EQ_DEC_MAIN" in response.content


@pytest.mark.asyncio
async def test_query_adql_structure(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.5"},
    )
    body = parse_qs(route.calls[0].request.content.decode())
    adql = body["QUERY"][0]
    assert "CONTAINS" in adql
    assert "CIRCLE" in adql
    assert "150" in adql
    assert "2" in adql
    assert "0.5" in adql
    assert "test.Object" in adql


@pytest.mark.asyncio
async def test_query_verb1_selects_minimal_columns(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1", "VERB": "1"},
    )
    body = parse_qs(route.calls[0].request.content.decode())
    adql = body["QUERY"][0]
    assert "objectId" in adql
    assert "coord_ra" in adql
    assert "coord_dec" in adql
    assert "flux" not in adql


@pytest.mark.asyncio
async def test_query_verb2_includes_extra_columns(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1", "VERB": "2"},
    )
    body = parse_qs(route.calls[0].request.content.decode())
    adql = body["QUERY"][0]
    assert "flux" in adql


@pytest.mark.asyncio
async def test_query_unknown_collection(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/unknown/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1"},
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_query_invalid_ra(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "400.0", "DEC": "2.2", "SR": "0.1"},
    )
    assert response.status_code == 200, response.text
    assert b"QUERY_STATUS" in response.content
    assert b"ERROR" in response.content


@pytest.mark.asyncio
async def test_query_invalid_dec(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "-95.0", "SR": "0.1"},
    )
    assert response.status_code == 200, response.text
    assert b"QUERY_STATUS" in response.content
    assert b"ERROR" in response.content


@pytest.mark.asyncio
async def test_query_sr_zero_sends_maxrec_zero(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0"},
    )
    body = parse_qs(route.calls[0].request.content.decode())
    assert body["MAXREC"][0] == "0"


@pytest.mark.asyncio
async def test_query_sr_too_large(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "181.0"},
    )
    assert response.status_code == 200, response.text
    assert b"ERROR" in response.content


@pytest.mark.asyncio
async def test_query_tap_votable_error_reported_as_failure(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    tap_error = (
        b'<?xml version="1.0"?>'
        b'<VOTABLE><RESOURCE type="results">'
        b'<INFO name="QUERY_STATUS" value="ERROR">bad query</INFO>'
        b"</RESOURCE></VOTABLE>"
    )
    respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=tap_error)
    )
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1"},
    )
    assert response.status_code == 200, response.text
    assert response.content == tap_error


@pytest.mark.asyncio
async def test_query_missing_required_param(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/test/query",
        params={"DEC": "2", "SR": "0.1"},
    )
    assert response.status_code == 200, response.text
    assert b"ERROR" in response.content


@pytest.mark.asyncio
async def test_query_sr_exceeds_max(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "20.0"},
    )
    assert response.status_code == 200, response.text
    assert b"ERROR" in response.content


@pytest.mark.asyncio
async def test_query_invalid_verb(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1", "VERB": "5"},
    )
    assert response.status_code == 200, response.text
    assert b"ERROR" in response.content


@pytest.mark.asyncio
async def test_query_sends_conesearch_ucd_map(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    await client.get(
        "/api/conesearch/test/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1"},
    )
    body = parse_qs(route.calls[0].request.content.decode())
    assert "CONESEARCH_UCD_MAP" in body
    ucd_map = body["CONESEARCH_UCD_MAP"][0]
    assert "ID_MAIN" in ucd_map
    assert "POS_EQ_RA_MAIN" in ucd_map
    assert "POS_EQ_DEC_MAIN" in ucd_map
