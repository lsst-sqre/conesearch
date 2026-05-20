"""Unit tests for VOTable services."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from conesearch.services.votable import votable_error


def test_votable_error_structure() -> None:
    result = votable_error("something went wrong")
    assert b"QUERY_STATUS" in result
    assert b"ERROR" in result
    assert b"something went wrong" in result


def test_votable_error_is_valid_xml() -> None:
    result = votable_error("test error")
    ET.fromstring(result)
