"""Unit tests for ConeSearchService."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest

from conesearch.config import CollectionConfig
from conesearch.models import ConeSearchParams, TimeConstraint
from conesearch.services.conesearch import ConeSearchService
from tests.support.mocks import make_collection


def test_columns_for_verb_1(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    result = service._columns_for_verb(1, collection)
    assert result == ["objectId", "coord_ra", "coord_dec"]


def test_columns_for_verb_2(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    result = service._columns_for_verb(2, collection)
    assert result == ["objectId", "coord_ra", "coord_dec", "flux"]


def test_columns_for_verb_3(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    result = service._columns_for_verb(3, collection)
    assert result == ["*"]


def test_columns_for_verb_1_fallback(service: ConeSearchService) -> None:
    coll = make_collection(verb1Columns=[], verb2Columns=[])
    result = service._columns_for_verb(1, coll)
    assert result == ["*"]


def test_build_adql_contains_circle(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    adql = service._build_adql(
        ra=150,
        dec=2,
        sr=0.5,
        time_constraint=None,
        verb=1,
        collection=collection,
    )
    assert "SELECT" in adql
    assert "test.Object" in adql
    assert "CONTAINS" in adql
    assert "POINT" in adql
    assert "CIRCLE" in adql
    assert "coord_ra" in adql
    assert "coord_dec" in adql
    assert "150" in adql
    assert "2" in adql
    assert "0.5" in adql


def test_build_adql_verb_respected(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    adql_v1 = service._build_adql(
        ra=0.0,
        dec=0.0,
        sr=0.1,
        time_constraint=None,
        verb=1,
        collection=collection,
    )
    adql_v2 = service._build_adql(
        ra=0.0,
        dec=0.0,
        sr=0.1,
        time_constraint=None,
        verb=2,
        collection=collection,
    )
    assert "flux" not in adql_v1
    assert "flux" in adql_v2


def test_build_adql_time_constraint(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    coll = make_collection(
        timeMinColumn="visit_time", timeMaxColumn="visit_time"
    )
    adql = service._build_adql(
        ra=150.0,
        dec=2.0,
        sr=0.1,
        time_constraint=TimeConstraint(start_mjd=60000.0, end_mjd=61000.0),
        verb=3,
        collection=coll,
    )
    assert "visit_time" in adql
    assert "60000.0" in adql
    assert "61000.0" in adql


def test_collection_config_rejects_invalid_table_name() -> None:
    with pytest.raises(ValueError, match="table"):
        make_collection(table="test.Object;drop")


def test_collection_config_rejects_invalid_column_name() -> None:
    with pytest.raises(ValueError, match=r"verb1Columns\.0"):
        make_collection(verb1Columns=["coord_ra desc"])


def test_time_constraint_parses_open_lower_bound() -> None:
    params = ConeSearchParams.model_validate(
        {"ra": 0, "dec": 0, "sr": 0.1, "time": "-Inf 61000.0"}
    )
    tc = params.time_constraint
    assert tc is not None
    assert tc.start_mjd is None
    assert tc.end_mjd == 61000.0


def test_time_constraint_parses_open_upper_bound() -> None:
    params = ConeSearchParams.model_validate(
        {"ra": 0, "dec": 0, "sr": 0.1, "time": "60000.0 +Inf"}
    )
    tc = params.time_constraint
    assert tc is not None
    assert tc.start_mjd == 60000.0
    assert tc.end_mjd is None


def test_time_constraint_parses_inf_case_insensitive() -> None:
    params = ConeSearchParams.model_validate(
        {"ra": 0, "dec": 0, "sr": 0.1, "time": "-inf +inf"}
    )
    tc = params.time_constraint
    assert tc is not None
    assert tc.start_mjd is None
    assert tc.end_mjd is None


@pytest.mark.asyncio
async def test_query_returns_error_votable_on_tap_failure(
    service: ConeSearchService, collection: CollectionConfig
) -> None:
    async def _tap_error(
        *args: object, **kwargs: object
    ) -> AsyncGenerator[bytes]:
        raise httpx.ReadTimeout("timed out")
        yield  # type: ignore[unreachable]

    service._execute_tap_query = _tap_error  # type: ignore[method-assign]

    result = b"".join(
        [
            chunk
            async for chunk in service.query(
                ra=150.0,
                dec=2.0,
                sr=0.1,
                time_constraint=None,
                verb=2,
                maxrec=None,
                collection=collection,
                send_ucd_map=True,
            )
        ]
    )

    assert b"QUERY_STATUS" in result
    assert b"timed out" in result
    cast(
        "AsyncMock", service._events.conesearch_query_failed.publish
    ).assert_awaited_once()


@pytest.mark.asyncio
async def test_query_publishes_success_event(
    service: ConeSearchService,
    collection: CollectionConfig,
) -> None:
    tap_response = b"<VOTABLE><TR><TD>1</TD></TR></VOTABLE>"

    async def _tap_success(
        *args: object, **kwargs: object
    ) -> AsyncGenerator[bytes]:
        yield tap_response

    service._execute_tap_query = _tap_success  # type: ignore[method-assign]

    result = b"".join(
        [
            chunk
            async for chunk in service.query(
                ra=150.0,
                dec=2.0,
                sr=0.1,
                time_constraint=None,
                verb=2,
                maxrec=None,
                collection=collection,
                send_ucd_map=True,
            )
        ]
    )

    assert result == tap_response
    cast(
        "AsyncMock", service._events.conesearch_query_succeeded.publish
    ).assert_awaited_once()
