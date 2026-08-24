"""Constants for conesearch."""

from pathlib import Path

__all__ = ["CONFIG_PATH", "CONFIG_PATH_ENV_VAR"]

CONFIG_PATH = Path("/etc/conesearch/config.yaml")
"""Default path to the configuration file."""

CONFIG_PATH_ENV_VAR = "CONESEARCH_CONFIG_PATH"
"""Environment variable to override the configuration file path."""
