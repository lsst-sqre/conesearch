"""Tests for the conesearch.handlers.external module and routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from httpx import AsyncClient

_TAP_VOTABLE = (
    Path(__file__).parent.parent / "data" / "votable" / "response_v2.xml"
).read_bytes()

_TAP_TABLES_XML = (
    Path(__file__).parent.parent / "data" / "votable" / "tap_tables.xml"
).read_bytes()

_TAP_SYNC_URL = "https://tap.example.com/api/tap/sync"
_TAP_TABLES_URL = "https://tap.example.com/api/tap/tables"


@pytest.mark.asyncio
async def test_get_availability(client: AsyncClient) -> None:
    response = await client.get("/api/conesearch/v2/availability")
    assert response.status_code == 200, response.text
    assert "application/xml" in response.headers["content-type"]
    assert b"<available>true</available>" in response.content


@pytest.mark.asyncio
async def test_get_capabilities(client: AsyncClient) -> None:
    response = await client.get("/api/conesearch/v2/capabilities")
    assert response.status_code == 200, response.text
    assert "application/xml" in response.headers["content-type"]
    assert b"ConeSearch" in response.content
    assert b"capabilities" in response.content
    assert b"availability" in response.content
    assert b"<maxSR>10.0</maxSR>" in response.content
    assert b"<maxRecords>100</maxRecords>" in response.content
    assert b"<verbosity>true</verbosity>" in response.content
    assert b"ivo://ivoa.net/SCS2#query-2.0" in response.content


@pytest.mark.asyncio
async def test_query(client: AsyncClient, respx_mock: respx.Router) -> None:
    respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1", "TABLE": "test.Object"},
    )
    body = parse_qs(respx_mock.calls[0].request.content.decode())
    assert response.status_code == 200, response.text
    assert "application/x-votable+xml" in response.headers["content-type"]
    assert b"meta.id;meta.main" in response.content
    assert b"pos.eq.ra;meta.main" in response.content
    assert b"pos.eq.dec;meta.main" in response.content
    assert "CONESEARCH_UCD_MAP" not in body


@pytest.mark.asyncio
async def test_query_adql_structure(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    await client.get(
        "/api/conesearch/v2/query",
        params={"RA": "150", "DEC": "2", "SR": "0.5", "TABLE": "test.Object"},
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
async def test_query_with_pos(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    route = respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"POS": "CIRCLE 150 2 0.1", "TABLE": "test.Object"},
    )
    body = parse_qs(route.calls[0].request.content.decode())
    adql = body["QUERY"][0]
    assert response.status_code == 200, response.text
    assert "application/x-votable+xml" in response.headers["content-type"]
    assert "150" in adql
    assert "2" in adql
    assert "0.1" in adql
    assert "CONTAINS" in adql


@pytest.mark.asyncio
async def test_query_pos_and_ra_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={
            "POS": "CIRCLE 150 2 0.1",
            "RA": "150",
            "TABLE": "test.Object",
        },
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_query_pos_invalid_format(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"POS": "CIRCLE 150 2", "TABLE": "test.Object"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_query_missing_position(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"TABLE": "test.Object"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_query_pos_out_of_range_ra(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"POS": "CIRCLE 400 2 0.1", "TABLE": "test.Object"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_query_pos_out_of_range_dec(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"POS": "CIRCLE 150 -95 0.1", "TABLE": "test.Object"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_query_sr_exceeds_max(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    respx_mock.post(_TAP_SYNC_URL).mock(
        return_value=httpx.Response(200, content=_TAP_VOTABLE)
    )
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"RA": "150", "DEC": "2", "SR": "20.0", "TABLE": "test.Object"},
    )
    assert response.status_code == 400, response.text
    assert respx_mock.calls.call_count == 0


@pytest.mark.asyncio
async def test_query_unknown_parameter(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={
            "RA": "150",
            "DEC": "2",
            "SR": "0.1",
            "TABLE": "test.Object",
            "UNKNOWN": "value",
        },
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_query_missing_table(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={"RA": "150", "DEC": "2", "SR": "0.1"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_query_unknown_table(client: AsyncClient) -> None:
    response = await client.get(
        "/api/conesearch/v2/query",
        params={
            "RA": "150",
            "DEC": "2",
            "SR": "0.1",
            "TABLE": "unknown.Table",
        },
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_get_tables(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    respx_mock.get(_TAP_TABLES_URL).mock(
        return_value=httpx.Response(200, content=_TAP_TABLES_XML)
    )
    response = await client.get("/api/conesearch/v2/tables")
    assert response.status_code == 200, response.text
    assert "application/xml" in response.headers["content-type"]
    assert b"test.Object" in response.content


@pytest.mark.asyncio
async def test_get_tables_filters_unserved_tables(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    respx_mock.get(_TAP_TABLES_URL).mock(
        return_value=httpx.Response(200, content=_TAP_TABLES_XML)
    )
    response = await client.get("/api/conesearch/v2/tables")
    assert b"test.Source" not in response.content


@pytest.mark.asyncio
async def test_get_tables_includes_all_columns(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    respx_mock.get(_TAP_TABLES_URL).mock(
        return_value=httpx.Response(200, content=_TAP_TABLES_XML)
    )
    response = await client.get("/api/conesearch/v2/tables")
    assert b"objectId" in response.content
    assert b"coord_ra" in response.content
    assert b"coord_dec" in response.content
    assert b"flux" in response.content


@pytest.mark.asyncio
async def test_get_tables_tap_error(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    respx_mock.get(_TAP_TABLES_URL).mock(return_value=httpx.Response(503))
    response = await client.get("/api/conesearch/v2/tables")
    assert response.status_code == 503
