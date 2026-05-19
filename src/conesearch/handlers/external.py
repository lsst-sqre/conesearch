"""Handlers for the app's external root, ``/conesearch/``."""

from __future__ import annotations

from typing import Annotated
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from safir.dependencies.logger import logger_dependency
from safir.metadata import get_metadata
from safir.slack.webhook import SlackRouteErrorHandler
from structlog.stdlib import BoundLogger
from vo_models.vosi.availability import Availability

from ..config import CollectionConfig, Config
from ..dependencies.conesearch import (
    collection_dependency,
    get_conesearch_params,
)
from ..dependencies.config import config_dependency
from ..dependencies.context import RequestContext, context_dependency
from ..models import ConeSearchParams, Index, IVOAStandardId

__all__ = ["external_router"]

external_router = APIRouter(route_class=SlackRouteErrorHandler)
"""FastAPI router for all external handlers."""

_CAPABILITIES_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<vosi:capabilities
    xmlns:vosi="http://www.ivoa.net/xml/VOSICapabilities/v1.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:cs="http://www.ivoa.net/xml/ConeSearch/v1.0">
  <capability standardID="{vosi_capabilities_id}">
    <interface type="vod:ParamHTTP">
      <accessURL use="full">{capabilities_url}</accessURL>
    </interface>
  </capability>
  <capability standardID="{vosi_availability_id}">
    <interface type="vod:ParamHTTP">
      <accessURL use="full">{availability_url}</accessURL>
    </interface>
  </capability>
  <capability xsi:type="cs:ConeSearch" standardID="{cone_search_id}">
    <interface type="vod:ParamHTTP" role="std" version="1.1">
      <accessURL use="base">{query_url}</accessURL>
    </interface>
    <maxSR>{max_sr}</maxSR>
    <maxRecords>{max_records}</maxRecords>
    <verbosity>true</verbosity>
  </capability>
</vosi:capabilities>
"""


def _capabilities_xml(
    capabilities_url: str,
    availability_url: str,
    query_url: str,
    collection: CollectionConfig,
    *,
    version: str = "1.1",
    standard_id: str = IVOAStandardId.CONE_SEARCH,
) -> bytes:
    # vo-models has no ConeSearch-specific capability class, so we use a
    # string template to include maxSR, maxRecords, and the cs:ConeSearch type.
    template = _CAPABILITIES_TEMPLATE.replace(
        'version="1.1"', f'version="{version}"'
    )
    return template.format(
        vosi_capabilities_id=IVOAStandardId.VOSI_CAPABILITIES,
        vosi_availability_id=IVOAStandardId.VOSI_AVAILABILITY,
        cone_search_id=standard_id,
        capabilities_url=escape(capabilities_url),
        availability_url=escape(availability_url),
        query_url=escape(query_url),
        max_sr=collection.max_sr,
        max_records=collection.max_records,
    ).encode()


@external_router.get(
    "/",
    description="Returns application metadata for the conesearch service.",
    response_model_exclude_none=True,
    summary="Application metadata",
)
async def get_index(
    logger: Annotated[BoundLogger, Depends(logger_dependency)],
    config: Annotated[Config, Depends(config_dependency)],
) -> Index:
    logger.info("Request for application metadata")
    metadata = get_metadata(
        package_name="conesearch",
        application_name=config.name,
    )
    return Index(metadata=metadata)


@external_router.get(
    "/{collection_name}/availability",
    description="VOSI availability resource for the ConeSearch service.",
    responses={200: {"content": {"application/xml": {}}}},
    summary="IVOA service availability",
)
async def get_availability(
    _collection: Annotated[CollectionConfig, Depends(collection_dependency)],
) -> Response:
    xml = Availability(available=True).to_xml(skip_empty=True)
    return Response(content=xml, media_type="application/xml")


@external_router.get(
    "/{collection_name}/capabilities",
    description="VOSI capabilities resource for the ConeSearch service.",
    responses={200: {"content": {"application/xml": {}}}},
    summary="IVOA service capabilities",
)
async def get_capabilities(
    collection_name: str,
    request: Request,
    collection: Annotated[CollectionConfig, Depends(collection_dependency)],
) -> Response:
    return Response(
        content=_capabilities_xml(
            capabilities_url=str(
                request.url_for(
                    "get_capabilities", collection_name=collection_name
                )
            ),
            availability_url=str(
                request.url_for(
                    "get_availability", collection_name=collection_name
                )
            ),
            query_url=str(
                request.url_for("query", collection_name=collection_name)
            ),
            collection=collection,
        ),
        media_type="application/xml",
    )


@external_router.get(
    "/{collection_name}/query",
    description="Execute a ConeSearch query (GET) against the specified "
    "collection.",
    responses={200: {"content": {"application/x-votable+xml": {}}}},
    summary="Execute a ConeSearch query (GET)",
)
@external_router.post(
    "/{collection_name}/query",
    description="Execute a ConeSearch query (POST) against the specified "
    "collection.",
    responses={200: {"content": {"application/x-votable+xml": {}}}},
    summary="Execute a ConeSearch query (POST)",
)
async def query(
    *,
    collection_name: str,
    params: Annotated[ConeSearchParams, Depends(get_conesearch_params)],
    collection: Annotated[CollectionConfig, Depends(collection_dependency)],
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> StreamingResponse:
    return StreamingResponse(
        context.factory.create_conesearch_service().query(
            ra=params.ra,
            dec=params.dec,
            sr=params.sr,
            time_constraint=params.time_constraint,
            verb=params.verb,
            maxrec=params.maxrec,
            collection=collection,
            send_ucd_map=True,
        ),
        media_type=params.responseformat,
        headers={
            "Content-Disposition": (
                f'inline; filename="conesearch-{collection_name}.xml"'
            )
        },
    )
