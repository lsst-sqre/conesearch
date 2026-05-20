"""Models for conesearch."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator
from safir.metadata import Metadata as SafirMetadata

__all__ = [
    "ConeSearchParams",
    "ConeSearchParamsV2",
    "IVOAStandardId",
    "Index",
    "ResponseFormat",
    "TimeConstraint",
]


class Index(BaseModel):
    """Metadata returned by the external root URL of the application."""

    metadata: SafirMetadata = Field(..., title="Package metadata")


class IVOAStandardId(StrEnum):
    """IVOA standard identifiers used in VOSI capabilities responses."""

    CONE_SEARCH = "ivo://ivoa.net/std/ConeSearch#query-1.1"
    CONE_SEARCH_V2 = "ivo://ivoa.net/SCS2#query-2.0"
    VOSI_AVAILABILITY = "ivo://ivoa.net/std/VOSI#availability"
    VOSI_CAPABILITIES = "ivo://ivoa.net/std/VOSI#capabilities"


class ResponseFormat(StrEnum):
    """MIME types accepted for the ConeSearch ``RESPONSEFORMAT`` parameter."""

    VOTABLE = "application/x-votable+xml"
    XML = "text/xml"
    XML_VOTABLE = "text/xml;content=x-votable"


DEFAULT_RESPONSEFORMAT = ResponseFormat.VOTABLE
"""Default value for the ConeSearch RESPONSEFORMAT parameter."""


class TimeConstraint(BaseModel):
    """Parsed time interval from a ConeSearch TIME parameter."""

    start_mjd: float | None = None
    end_mjd: float | None = None


def _parse_time_string(value: str) -> TimeConstraint:
    """Parse a DALI TIME interval string into a `TimeConstraint`.

    Parameters
    ----------
    value
        A space-separated string in one of these forms:

        - A single MJD float (e.g. ``"60000.0"``), treated as an
          exact instant.
        - Two MJD floats (e.g. ``"60000.0 61000.0"``).
        - Open-ended bounds using ``-Inf`` or ``+Inf``
          (e.g. ``"-Inf 61000.0"``), which map to ``None``.

    Returns
    -------
    TimeConstraint
        Parsed interval with ``start_mjd`` and ``end_mjd``.

    Raises
    ------
    ValueError
        If the string contains anything other than one or two
        space-separated tokens.
    """
    parts = value.split()
    if len(parts) == 1:
        mjd = float(parts[0])
        return TimeConstraint(start_mjd=mjd, end_mjd=mjd)
    if len(parts) != 2:
        raise ValueError(
            "TIME must be a single value or two space-separated values"
        )
    start_raw, end_raw = parts
    start = None if start_raw.lower() == "-inf" else float(start_raw)
    end = None if end_raw.lower() == "+inf" else float(end_raw)
    return TimeConstraint(start_mjd=start, end_mjd=end)


class ConeSearchParams(BaseModel):
    """Parameters for a ConeSearch query.

    ``maxrec=None`` uses the collection default.
    ``maxrec=0`` is a valid client request that returns zero rows
    (metadata only).  The ``time`` field is kept as ``str | None`` so
    FastAPI binds it as a plain query parameter and `time_constraint`
    can be used to access the parsed value.
    """

    model_config = ConfigDict(extra="ignore")

    ra: Annotated[float, Field(ge=0, le=360)]
    dec: Annotated[float, Field(ge=-90, le=90)]
    sr: Annotated[float, Field(ge=0, le=180.0)]
    verb: Annotated[int, Field(default=2, ge=1, le=3)]
    maxrec: Annotated[int | None, Field(ge=0)] = None
    time: str | None = None
    responseformat: ResponseFormat = DEFAULT_RESPONSEFORMAT

    _time_constraint: TimeConstraint | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _parse_time(self) -> Self:
        if self.time is not None:
            self._time_constraint = _parse_time_string(self.time)
        return self

    @property
    def time_constraint(self) -> TimeConstraint | None:
        """Return the parsed TIME parameter as a `TimeConstraint` object."""
        return self._time_constraint


class ConeSearchParamsV2(ConeSearchParams):
    """Parameters for a ConeSearch v2 query."""

    model_config = ConfigDict(extra="forbid")

    pos: str | None = None
    table: Annotated[str, Field(min_length=1)]
    ra: Annotated[float | None, Field(ge=0, le=360)] = None  # type: ignore[assignment]
    dec: Annotated[float | None, Field(ge=-90, le=90)] = None  # type: ignore[assignment]
    sr: Annotated[float | None, Field(ge=0, le=180.0)] = None  # type: ignore[assignment]
