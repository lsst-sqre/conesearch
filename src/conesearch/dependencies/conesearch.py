"""ConeSearch collection and parameter dependencies for FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

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


async def get_conesearch_params_v2(
    request: Request,
    params: Annotated[ConeSearchParamsV2, Depends()],
) -> ConeSearchParamsV2:
    """Parse GET and POST ConeSearch v2 parameters."""
    if request.method != "POST":
        return params

    data = await _parse_form(request)
    return ConeSearchParamsV2.model_validate(data)


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
