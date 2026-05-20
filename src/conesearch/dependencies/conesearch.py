"""ConeSearch collection and parameter dependencies for FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from pydantic import ValidationError

from conesearch.config import CollectionConfig, Config
from conesearch.dependencies.config import config_dependency
from conesearch.models import ConeSearchParams, ConeSearchParamsV2

__all__ = [
    "collection_dependency",
    "collection_dependency_v2",
    "get_conesearch_params",
    "get_conesearch_params_v2",
]


async def _parse_form(request: Request) -> dict[str, str]:
    """Parse form data from a POST request, converting keys to lowercase."""
    form = await request.form()
    return {k.lower(): v for k, v in form.items() if isinstance(v, str)}


async def collection_dependency(
    collection_name: str,
    config: Annotated[Config, Depends(config_dependency)],
) -> CollectionConfig:
    """Resolve a collection name to its configuration.

    Raises
    ------
    HTTPException
        With status 404 if the collection name is not configured.
    """
    collection = config.collections.get(collection_name)
    if collection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown collection '{collection_name}'",
        )
    return collection


def _apply_pos_circle(params: ConeSearchParamsV2) -> None:
    """Parse a POS=CIRCLE string and set ra, dec, sr on params in place.

    Raises
    ------
    HTTPException
        With status 422 for malformed, non-numeric, or out-of-range values.
    """
    if params.pos is None:
        return
    parts = params.pos.split()
    if len(parts) != 4 or parts[0].upper() != "CIRCLE":
        raise HTTPException(
            status_code=422,
            detail="POS must be in the form 'CIRCLE lon lat radius'",
        )
    try:
        ra, dec, sr = float(parts[1]), float(parts[2]), float(parts[3])
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail="POS CIRCLE parameters must be numeric",
        ) from e
    if not 0 <= ra <= 360:
        raise HTTPException(
            status_code=422, detail=f"POS RA {ra} must be between 0 and 360"
        )
    if not -90 <= dec <= 90:
        raise HTTPException(
            status_code=422,
            detail=f"POS DEC {dec} must be between -90 and 90",
        )
    if not 0 <= sr <= 180:
        raise HTTPException(
            status_code=422, detail=f"POS SR {sr} must be between 0 and 180"
        )
    params.ra, params.dec, params.sr = ra, dec, sr


async def get_conesearch_params_v2(request: Request) -> ConeSearchParamsV2:
    """Parse and validate GET and POST ConeSearch v2 parameters.

    Raises
    ------
    HTTPException
        With status 422 for invalid or conflicting parameters.
    """
    if request.method == "POST":
        data: dict[str, str] = await _parse_form(request)
    else:
        data = dict(request.query_params)

    try:
        params = ConeSearchParamsV2.model_validate(data)
    except ValidationError as e:
        errors = e.errors()
        status = (
            400
            if any(err["type"] == "extra_forbidden" for err in errors)
            else 422
        )
        raise HTTPException(status_code=status, detail=errors) from e

    has_pos = params.pos is not None
    has_radecsr = all(
        x is not None for x in [params.ra, params.dec, params.sr]
    )
    has_partial = (
        any(x is not None for x in [params.ra, params.dec, params.sr])
        and not has_radecsr
    )

    if has_pos and (has_radecsr or has_partial):
        raise HTTPException(
            status_code=400,
            detail="POS cannot be used together with RA, DEC, or SR",
        )
    if has_partial:
        raise HTTPException(
            status_code=422,
            detail="RA, DEC, and SR must all be provided together",
        )
    if not has_pos and not has_radecsr:
        raise HTTPException(
            status_code=422,
            detail="Either POS=CIRCLE or RA/DEC/SR is required",
        )
    if has_pos:
        _apply_pos_circle(params)

    return params


async def collection_dependency_v2(
    params: Annotated[ConeSearchParamsV2, Depends(get_conesearch_params_v2)],
    config: Annotated[Config, Depends(config_dependency)],
) -> CollectionConfig:
    """Resolve a TABLE parameter to its collection configuration.

    Raises
    ------
    HTTPException
        With status 400 if no collection is configured for the given table.
    """
    for collection in config.collections.values():
        if collection.table == params.table:
            return collection
    raise HTTPException(
        status_code=400,
        detail=f"Unknown table '{params.table}'",
    )


async def get_conesearch_params(
    request: Request,
    params: Annotated[ConeSearchParams, Depends()],
) -> ConeSearchParams:
    """Parse GET and POST ConeSearch parameters."""
    if request.method != "POST":
        return params

    data = await _parse_form(request)
    return ConeSearchParams.model_validate(data)
