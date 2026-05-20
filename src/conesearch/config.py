"""Configuration definition."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict
from safir.logging import (
    LogLevel,
    Profile,
    configure_logging,
    configure_uvicorn_logging,
)
from safir.metrics import MetricsConfiguration, metrics_configuration_factory

__all__ = ["CollectionConfig", "Config"]

_ADQL_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_ADQL_TABLE_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$"


class CollectionConfig(BaseModel):
    """Configuration for a single ConeSearch collection."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )

    _tap_url: str = PrivateAttr(default="")

    table: Annotated[
        str,
        Field(
            title="TAP table name",
            description="Fully qualified TAP table name (e.g. dp1.Object)",
            pattern=_ADQL_TABLE_PATTERN,
        ),
    ]

    id_column: Annotated[
        str, Field(title="ID column", pattern=_ADQL_IDENTIFIER_PATTERN)
    ]

    ra_column: Annotated[
        str, Field(title="RA column", pattern=_ADQL_IDENTIFIER_PATTERN)
    ]

    dec_column: Annotated[
        str, Field(title="Dec column", pattern=_ADQL_IDENTIFIER_PATTERN)
    ]

    time_min_column: Annotated[
        str | None,
        Field(
            title="Time min column",
            description=(
                "Column containing the minimum time value for the record. "
                "If not set, no time constraint will be applied."
            ),
            pattern=_ADQL_IDENTIFIER_PATTERN,
        ),
    ] = None

    time_max_column: Annotated[
        str | None,
        Field(
            title="Time max column",
            description=(
                "Column containing the maximum time value for the record. "
                "If not set, no time constraint will be applied."
            ),
            pattern=_ADQL_IDENTIFIER_PATTERN,
        ),
    ] = None

    max_sr: Annotated[
        float,
        Field(
            title="Maximum search radius",
            description="Maximum allowed search radius in decimal degrees",
            ge=0.0,
            le=180.0,
        ),
    ] = 180.0

    max_records: Annotated[
        int,
        Field(
            title="Maximum records",
            description="Maximum number of rows returned by a query",
            gt=0,
        ),
    ] = 10000

    verb1_columns: Annotated[
        list[Annotated[str, Field(pattern=_ADQL_IDENTIFIER_PATTERN)]],
        Field(
            default_factory=list,
            title="VERB=1 columns",
            description=(
                "Columns returned for VERB=1 (minimum). If empty, falls "
                "back to all columns."
            ),
        ),
    ]

    verb2_columns: Annotated[
        list[Annotated[str, Field(pattern=_ADQL_IDENTIFIER_PATTERN)]],
        Field(
            default_factory=list,
            title="VERB=2 columns",
            description=(
                "Columns returned for VERB=2 (default). If empty, falls "
                "back to all columns."
            ),
        ),
    ]

    def columns_for_verb(self, verb: int) -> list[str]:
        """Return the configured column list for the given VERB level.

        Parameters
        ----------
        verb
            ConeSearch VERB level (1, 2, or 3).

        Returns
        -------
        list[str]
            The configured column names for this verb level. An empty list
            indicates the caller should select all columns.
        """
        match verb:
            case 1:
                return self.verb1_columns
            case 2:
                return self.verb2_columns
            case _:
                return []

    @property
    def tap_sync_url(self) -> str:
        """The URL for the TAP sync endpoint.

        Returns
        -------
        str
            Resolved TAP base URL with ``/sync`` appended.

        Raises
        ------
        RuntimeError
            If called before TAP URLs have been resolved at startup.
        """
        if not self._tap_url:
            raise RuntimeError(
                "TAP URL has not been resolved yet;"
                " ensure startup completed successfully"
            )
        return self._tap_url.rstrip("/") + "/sync"

    @property
    def ucd_map(self) -> dict[str, str]:
        """Mapping of column names to their required ConeSearch UCDs.

        Returns
        -------
        dict[str, str]
            Maps each of the three required columns (id, RA, dec) to
            its ConeSearch 1.x UCD string (``ID_MAIN``,
            ``POS_EQ_RA_MAIN``, ``POS_EQ_DEC_MAIN``).
        """
        return {
            self.id_column: "ID_MAIN",
            self.ra_column: "POS_EQ_RA_MAIN",
            self.dec_column: "POS_EQ_DEC_MAIN",
        }


class Config(BaseSettings):
    """Configuration for conesearch."""

    model_config = SettingsConfigDict(extra="forbid", populate_by_name=True)

    log_level: Annotated[
        LogLevel,
        Field(
            title="Log level of the application's logger",
            validation_alias="logLevel",
        ),
    ] = LogLevel.INFO

    profile: Annotated[
        Profile,
        Field(title="Application logging profile"),
    ] = Profile.production

    name: Annotated[
        str,
        Field(title="Name of application"),
    ] = "conesearch"

    path_prefix: Annotated[
        str,
        Field(
            title="URL prefix for the ConeSearch API",
            validation_alias="pathPrefix",
        ),
    ] = "/api/conesearch"

    slack_webhook: Annotated[
        str | None,
        Field(
            title="Slack webhook for alerts",
            description=(
                "If set, uncaught exceptions will be reported to Slack "
                "via this webhook"
            ),
            validation_alias=AliasChoices(
                "CONESEARCH_SLACK_WEBHOOK", "slackWebhook"
            ),
        ),
    ] = None

    metrics: Annotated[
        MetricsConfiguration,
        Field(
            default_factory=metrics_configuration_factory,
            title="Metrics configuration",
            description="Configuration for reporting metrics to Kafka",
        ),
    ]

    collections: Annotated[
        dict[str, CollectionConfig],
        Field(
            min_length=1,
            title="ConeSearch collections",
            description=(
                "Mapping of collection names to their configuration. "
                "Each collection corresponds to a named catalog (e.g. dp1)"
            ),
        ),
    ]

    def configure_logging(self) -> None:
        """Configure logging based on the service configuration."""
        configure_logging(
            profile=self.profile,
            log_level=self.log_level,
            name="conesearch",
        )
        if self.profile == Profile.production:
            configure_uvicorn_logging(self.log_level)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Construct a `Config` from a YAML configuration file."""
        return cls.model_validate(yaml.safe_load(path.read_text()))
