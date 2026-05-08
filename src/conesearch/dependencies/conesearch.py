"""ConeSearch collection and parameter dependencies for FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from conesearch.config import CollectionConfig, Config
from conesearch.dependencies.config import config_dependency
from conesearch.models import ConeSearchParams

__all__ = [
    "collection_dependency",
    "get_conesearch_params",
]


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


async def get_conesearch_params(
    request: Request,
    params: Annotated[ConeSearchParams, Depends()],
) -> ConeSearchParams:
    """Parse GET and POST ConeSearch parameters."""
    if request.method != "POST":
        return params

    form = await request.form()
    data: dict[str, str] = {}
    for key, value in form.items():
        if not isinstance(value, str):
            raise TypeError("File upload not supported")
        data[key.lower()] = value
    return ConeSearchParams.model_validate(data)
