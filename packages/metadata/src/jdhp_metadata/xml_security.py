"""One parser for every XML the platform reads: entities and DTDs disabled (SEC-17)."""

from __future__ import annotations

import xml.etree.ElementTree as ET  # nosec B405  # types only; parsing uses defusedxml

from defusedxml.ElementTree import fromstring as _defused_fromstring


class UnsafeXmlError(ValueError):
    """The document used a construct the platform refuses (entities, DTD, external references)."""


def parse_xml(data: bytes | str) -> ET.Element:
    """Parse untrusted XML. Any entity or DTD trick raises UnsafeXmlError."""
    try:
        element = _defused_fromstring(
            data, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except ET.ParseError:
        raise
    except Exception as exc:  # defusedxml raises its own exception family
        raise UnsafeXmlError(str(exc)) from exc
    return element
