"""Handlers for the SCS2 external routes, ``/conesearch/v2/``."""

from __future__ import annotations

from typing import Annotated
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from safir.slack.webhook import SlackRouteErrorHandler
from vo_models.vosi.availability import Availability

from ..config import CollectionConfig, Config
from ..dependencies.conesearch import (
    collection_dependency_v2,
    get_conesearch_params_v2,
)
from ..dependencies.config import config_dependency
from ..dependencies.context import RequestContext, context_dependency
from ..models import ConeSearchParamsV2, IVOAStandardId

__all__ = ["external_router_v2"]

_CS_CAPABILITY_BLOCK = """\
  <capability xsi:type="cs:ConeSearch" standardID="{cone_search_id}">
    <interface type="vod:ParamHTTP" role="std" version="2.0">
      <accessURL use="base">{query_url}</accessURL>
    </interface>
    <maxSR>{max_sr}</maxSR>
    <maxRecords>{max_records}</maxRecords>
    <verbosity>true</verbosity>
  </capability>"""

_CAPABILITIES_V2_HEADER = """\
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
  </capability>"""

_CAPABILITIES_V2_FOOTER = "\n</vosi:capabilities>\n"


def _capabilities_xml_v2(
    capabilities_url: str,
    availability_url: str,
    query_url: str,
    config: Config,
) -> bytes:
    header = _CAPABILITIES_V2_HEADER.format(
        vosi_capabilities_id=IVOAStandardId.VOSI_CAPABILITIES,
        vosi_availability_id=IVOAStandardId.VOSI_AVAILABILITY,
        capabilities_url=escape(capabilities_url),
        availability_url=escape(availability_url),
    )
    blocks = "\n".join(
        _CS_CAPABILITY_BLOCK.format(
            cone_search_id=IVOAStandardId.CONE_SEARCH_V2,
            query_url=escape(query_url),
            max_sr=collection.max_sr,
            max_records=collection.max_records,
        )
        for collection in config.collections.values()
    )
    return (header + "\n" + blocks + _CAPABILITIES_V2_FOOTER).encode()


external_router_v2 = APIRouter(route_class=SlackRouteErrorHandler)
"""FastAPI router for all SCS2 external handlers."""


@external_router_v2.get(
    "/availability",
    description="VOSI availability resource for the SCS2 service.",
    responses={200: {"content": {"application/xml": {}}}},
    summary="IVOA service availability",
)
async def get_availability_v2() -> Response:
    xml = Availability(available=True).to_xml(skip_empty=True)
    return Response(content=xml, media_type="application/xml")


@external_router_v2.get(
    "/capabilities",
    description="VOSI capabilities resource for the SCS2 service.",
    responses={200: {"content": {"application/xml": {}}}},
    summary="IVOA service capabilities",
)
async def get_capabilities_v2(
    request: Request,
    config: Annotated[Config, Depends(config_dependency)],
) -> Response:
    return Response(
        content=_capabilities_xml_v2(
            capabilities_url=str(request.url_for("get_capabilities_v2")),
            availability_url=str(request.url_for("get_availability_v2")),
            query_url=str(request.url_for("query_v2")),
            config=config,
        ),
        media_type="application/xml",
    )


@external_router_v2.get(
    "/query",
    description="Execute a SCS2 query (GET).",
    responses={200: {"content": {"application/x-votable+xml": {}}}},
    summary="Execute a SCS2 query (GET)",
)
@external_router_v2.post(
    "/query",
    description="Execute a SCS2 query (POST).",
    responses={200: {"content": {"application/x-votable+xml": {}}}},
    summary="Execute a SCS2 query (POST)",
)
async def query_v2(
    *,
    params: Annotated[ConeSearchParamsV2, Depends(get_conesearch_params_v2)],
    collection: Annotated[CollectionConfig, Depends(collection_dependency_v2)],
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
            send_ucd_map=False,
        ),
        media_type=params.responseformat,
        headers={
            "Content-Disposition": (
                f'inline; filename="conesearch-{params.table}.xml"'
            )
        },
    )
