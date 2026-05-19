"""ConeSearch query service."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from datetime import timedelta

import httpx
from structlog.stdlib import BoundLogger

from conesearch.config import CollectionConfig
from conesearch.events import (
    ConeSearchQueryFailed,
    ConeSearchQuerySucceeded,
    Events,
)
from conesearch.models import TimeConstraint
from conesearch.services.adql import ADQLQuery
from conesearch.services.votable import votable_error

__all__ = ["ConeSearchService"]

_PEEK_SIZE = 8192
"""Bytes to buffer from the TAP response before checking for errors."""


class ConeSearchService:
    """Executes a ConeSearch query against a TAP service.

    Parameters
    ----------
    http_client
        Shared async HTTP client used for TAP sync requests.
    delegated_token
        Gafaelfawr delegated token passed as a Bearer credential to TAP.
    logger
        Bound logger for structured log output.
    events
        Metrics event publishers for query success and failure.
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

    @staticmethod
    def _effective_maxrec(
        requested: int | None,
        sr: float,
        collection: CollectionConfig,
    ) -> int:
        """Determine the effective MAXREC for a query.

        Parameters
        ----------
        requested
            Client-supplied MAXREC value, or ``None`` to use the
            collection default.
        sr
            Search radius in degrees. SR=0 means "metadata only" per the
            ConeSearch spec.
        collection
            Collection configuration supplying the maximum allowed value.

        Returns
        -------
        int
            The minimum between the requested value and the collection maximum.
        """
        if sr == 0:
            return 0
        if requested is None:
            return collection.max_records
        return min(requested, collection.max_records)

    def _columns_for_verb(
        self,
        verb: int,
        collection: CollectionConfig,
    ) -> list[str]:
        """Return the SELECT column list for the given VERB level.

        Falls back to ``["*"]`` when VERB=3 is requested or when the
        collection has no columns configured for the requested level.

        Parameters
        ----------
        verb
            ConeSearch VERB parameter (1, 2, or 3).
        collection
            Collection configuration supplying the per-verb column lists.

        Returns
        -------
        list[str]
            Column names to use in the SELECT clause, or ``["*"]`` to
            select all columns.
        """
        columns = collection.columns_for_verb(verb)
        if verb >= 3 or not columns:
            self._logger.debug(
                "Using SELECT * for VERB level",
                verb=verb,
                collection_table=collection.table,
            )
            return ["*"]
        return columns

    def _time_clauses(
        self,
        time_constraint: TimeConstraint | None,
        collection: CollectionConfig,
    ) -> list[str]:
        """Build ADQL WHERE predicates for a time constraint.

        Generates predicates for time bounds that are both present in the
        constraint and backed by a column in the collection,
        otherwise returns an empty list.

        Parameters
        ----------
        time_constraint
            Parsed MJD interval, or ``None`` for no time filtering.
            ``start_mjd`` or ``end_mjd`` may be ``None`` for open-ended
            intervals.
        collection
            Collection configuration supplying ``time_min_column`` and
            ``time_max_column``.

        Returns
        -------
        list[str]
            Zero, one, or two ADQL predicate strings.
        """
        if time_constraint is None:
            return []

        clauses: list[str] = []

        if (
            time_constraint.start_mjd is not None
            and collection.time_max_column
        ):
            clauses.append(
                f"{collection.time_max_column} >= {time_constraint.start_mjd}"
            )

        if time_constraint.end_mjd is not None and collection.time_min_column:
            clauses.append(
                f"{collection.time_min_column} <= {time_constraint.end_mjd}"
            )

        return clauses

    @staticmethod
    def _spatial_clause(
        ra: float,
        dec: float,
        sr: float,
        collection: CollectionConfig,
    ) -> str:
        """Build the ADQL CONTAINS/CIRCLE spatial predicate.

        Parameters
        ----------
        ra
            Right ascension (decimal degrees).
        dec
            Declination (decimal degrees).
        sr
            Search radius (decimal degrees).
        collection
            Collection configuration supplying the RA and Dec column names.

        Returns
        -------
        str
            An ADQL boolean expression of the form
            ``1 = CONTAINS(POINT(...), CIRCLE(...))``.
        """
        return "\n".join(
            [
                "1 = CONTAINS(",
                (
                    f"    POINT('ICRS', "
                    f"{collection.ra_column}, "
                    f"{collection.dec_column}),"
                ),
                f"    CIRCLE('ICRS', {ra:.10f}, {dec:.10f}, {sr:.10f})",
                ")",
            ]
        )

    def _build_adql(
        self,
        ra: float,
        dec: float,
        sr: float,
        time_constraint: TimeConstraint | None,
        verb: int,
        collection: CollectionConfig,
    ) -> str:
        """Build the ADQL query string for a cone search.

        Parameters
        ----------
        ra
            Right ascension (decimal degrees).
        dec
            Declination (decimal degrees).
        sr
            Search radius (decimal degrees).
        time_constraint
            Optional MJD time interval. Only applied when the collection
            has ``time_min_column`` or ``time_max_column`` configured.
        verb
            ConeSearch VERB level controlling which columns are selected.
        collection
            Collection configuration.

        Returns
        -------
        str
            A complete ADQL SELECT statement.
        """
        return (
            ADQLQuery(table=collection.table)
            .select(*self._columns_for_verb(verb=verb, collection=collection))
            .where(
                self._spatial_clause(
                    ra=ra, dec=dec, sr=sr, collection=collection
                )
            )
            .where(*self._time_clauses(time_constraint, collection))
            .render()
        )

    async def _fail(
        self,
        error: str,
        duration: timedelta,
        *,
        response: bytes | None = None,
    ) -> bytes:
        """Log a warning, publish a failed-query event, and return a response.

        Parameters
        ----------
        error
            Human-readable error description.
        duration
            Elapsed time from the start of the query to the failure.
        response
            VOTable bytes to return. Defaults to a freshly built
            ``QUERY_STATUS=ERROR`` document when not provided.

        Returns
        -------
        bytes
            VOTable error response.
        """
        self._logger.warning(
            "ConeSearch query failed",
            error=error,
            total_duration_seconds=round(duration.total_seconds(), 3),
        )
        await self._events.conesearch_query_failed.publish(
            ConeSearchQueryFailed(
                username=self._username,
                duration=duration,
                error=error,
            )
        )
        return response if response is not None else votable_error(error)

    async def _execute_tap_query(
        self,
        adql: str,
        collection: CollectionConfig,
        maxrec: int,
        *,
        send_ucd_map: bool,
    ) -> AsyncGenerator[bytes]:
        """Submit a synchronous TAP query and stream the response.

        Parameters
        ----------
        adql
            The ADQL query string to execute.
        collection
            Collection configuration supplying the TAP sync URL and UCD map.
        maxrec
            Row limit passed to the TAP service via the ``MAXREC`` parameter.
        send_ucd_map
            If ``True``, passes ``CONESEARCH_UCD_MAP`` so TAP injects
            ConeSearch 1.x UCDs. Pass ``False`` for SCS2 routes where TAP's
            native UCD1+ values should be preserved.

        Yields
        ------
        bytes
            Raw bytes from the TAP response body.

        Raises
        ------
        RuntimeError
            If the TAP service returns a non-200 status code.
        httpx.HTTPError
            If the HTTP request itself fails (timeout, connection error, etc.).
        """
        self._logger.debug(
            "Executing TAP query", tap_url=collection.tap_sync_url, adql=adql
        )
        data: dict[str, str | int] = {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": adql,
            "MAXREC": maxrec,
        }
        if send_ucd_map:
            data["CONESEARCH_UCD_MAP"] = ",".join(
                f"{col}:{ucd}" for col, ucd in collection.ucd_map.items()
            )
        async with self._http_client.stream(
            "POST",
            collection.tap_sync_url,
            data=data,
            headers={"Authorization": f"Bearer {self._delegated_token}"},
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise RuntimeError(
                    f"TAP returned {response.status_code}:"
                    f" {body[:200].decode()}"
                )
            async for chunk in response.aiter_bytes():
                yield chunk

    async def _peek_tap_response(
        self, tap_stream: AsyncGenerator[bytes]
    ) -> tuple[bytes, bool]:
        """Buffer the opening bytes of a TAP stream and detect errors.

        Parameters
        ----------
        tap_stream
            Async generator yielding raw bytes from the TAP response.

        Returns
        -------
        tuple[bytes, bool]
            The buffered prefix and whether ``QUERY_STATUS=ERROR`` was found.
        """
        first_chunk = b""
        async for chunk in tap_stream:
            first_chunk += chunk
            if len(first_chunk) >= _PEEK_SIZE:
                break
        return first_chunk, b'value="ERROR"' in first_chunk

    async def query(
        self,
        ra: float,
        dec: float,
        sr: float,
        time_constraint: TimeConstraint | None,
        verb: int,
        maxrec: int | None,
        collection: CollectionConfig,
        *,
        send_ucd_map: bool,
    ) -> AsyncGenerator[bytes]:
        """Execute a cone search and stream a ConeSearch-compliant VOTable.

        Streams the raw TAP response without buffering the result set.
        UCD injection is left to the TAP service via ``CONESEARCH_UCD_MAP``
        when ``send_ucd_map`` is ``True`` (SCS 1.1). SCS2 routes pass
        ``False`` to preserve native UCD1+ values from TAP.

        The first ``_PEEK_SIZE`` bytes are buffered to detect
        ``QUERY_STATUS=ERROR`` responses from TAP. On any failure a complete
        VOTable error document is yielded with ``QUERY_STATUS=ERROR`` as per
        the ConeSearch specification.

        Parameters
        ----------
        ra
            Right ascension (decimal degrees).
        dec
            Declination (decimal degrees).
        sr
            Search radius (decimal degrees).
        time_constraint
            Optional MJD time interval filter, or ``None`` for no time
            constraint.
        verb
            ConeSearch VERB level (1-3) controlling column verbosity.
        maxrec
            Maximum number of rows to return, or ``None`` to use the
            collection default.
        collection
            Configuration for the target collection.
        send_ucd_map
            If ``True``, passes ``CONESEARCH_UCD_MAP`` to TAP so it injects
            ConeSearch 1.x UCDs. Pass ``False`` for SCS2 routes.

        Yields
        ------
        bytes
            VOTable bytes, either streamed query results or a complete
            error document.
        """
        start = time.monotonic()

        self._logger.info(
            "ConeSearch query",
            table=collection.table,
            ra=ra,
            dec=dec,
            sr=sr,
            time_start=time_constraint.start_mjd if time_constraint else None,
            time_end=time_constraint.end_mjd if time_constraint else None,
            verb=verb,
            maxrec=maxrec,
        )

        if sr > collection.max_sr:
            error = (
                f"SR {sr} exceeds maximum search radius"
                f" {collection.max_sr} for '{collection.table}'"
            )
            yield await self._fail(
                error, timedelta(seconds=time.monotonic() - start)
            )
            return

        maxrec_value = self._effective_maxrec(
            requested=maxrec, sr=sr, collection=collection
        )
        adql = self._build_adql(
            ra=ra,
            dec=dec,
            sr=sr,
            time_constraint=time_constraint,
            verb=verb,
            collection=collection,
        )

        tap_start = time.monotonic()
        tap_stream = self._execute_tap_query(
            adql=adql,
            collection=collection,
            maxrec=maxrec_value,
            send_ucd_map=send_ucd_map,
        )

        try:
            first_chunk, has_error = await self._peek_tap_response(tap_stream)
        except (httpx.HTTPError, RuntimeError) as e:
            yield await self._fail(
                str(e), timedelta(seconds=time.monotonic() - start)
            )
            return

        tap_duration = timedelta(seconds=time.monotonic() - tap_start)

        if has_error:
            rest = b"".join([chunk async for chunk in tap_stream])
            yield await self._fail(
                "TAP query returned QUERY_STATUS=ERROR",
                timedelta(seconds=time.monotonic() - start),
                response=first_chunk + rest,
            )
            return

        total_duration = timedelta(seconds=time.monotonic() - start)
        self._logger.info(
            "ConeSearch query completed",
            username=self._username,
            tap_duration_seconds=round(tap_duration.total_seconds(), 3),
            total_duration_seconds=round(total_duration.total_seconds(), 3),
        )
        await self._events.conesearch_query_succeeded.publish(
            ConeSearchQuerySucceeded(
                duration=total_duration,
                tap_duration=tap_duration,
                username=self._username,
            )
        )

        yield first_chunk
        async for chunk in tap_stream:
            yield chunk
