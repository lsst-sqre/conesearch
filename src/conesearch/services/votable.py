"""VOTable utilities for ConeSearch responses."""

from __future__ import annotations

from xml.sax.saxutils import escape

__all__ = ["votable_error"]

_VOTABLE_ERROR_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
  <RESOURCE type="results">
    <INFO name="QUERY_STATUS" value="ERROR">{message}</INFO>
  </RESOURCE>
</VOTABLE>
"""


def votable_error(message: str) -> bytes:
    """Return a ConeSearch-compliant VOTable error response as bytes.

    Parameters
    ----------
    message
        Error message to include in the VOTable INFO element.

    Returns
    -------
    bytes
        UTF-8 encoded VOTable XML with ``QUERY_STATUS`` set to ``ERROR``.
    """
    escaped = escape(message)
    return _VOTABLE_ERROR_TEMPLATE.format(message=escaped).encode()
