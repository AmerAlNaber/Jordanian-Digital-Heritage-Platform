"""Localized API messages. Arabic is the default locale; English is the second (INT-1).

The API returns error titles and details in the negotiated locale. User-facing interface
strings live in the web application; these catalogs cover only what the API itself says.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources

from jdhp_api.core.config import SUPPORTED_LOCALES

DEFAULT_LOCALE = "ar"


@cache
def _catalog(locale: str) -> dict[str, str]:
    text = resources.files("jdhp_api.core.messages").joinpath(f"{locale}.json").read_text("utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):  # pragma: no cover - the files are part of the package
        msg = f"message catalog {locale} is not an object"
        raise TypeError(msg)
    return {str(k): str(v) for k, v in data.items()}


def negotiate_locale(accept_language: str | None, default: str = DEFAULT_LOCALE) -> str:
    """Pick the best supported locale from an Accept-Language header, Arabic by default."""
    if not accept_language:
        return default
    candidates: list[tuple[float, int, str]] = []
    for index, part in enumerate(accept_language.split(",")):
        pieces = part.strip().split(";")
        tag = pieces[0].strip().lower()
        if not tag:
            continue
        quality = 1.0
        for param in pieces[1:]:
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        candidates.append((-quality, index, tag))
    for _, _, tag in sorted(candidates):
        primary = tag.split("-")[0]
        if tag == "*":
            return default
        if primary in SUPPORTED_LOCALES:
            return primary
    return default


def translate(locale: str, key: str, **params: object) -> str:
    """Look up a message, falling back to the default locale and then to the key itself."""
    for candidate in (locale, DEFAULT_LOCALE):
        catalog = _catalog(candidate)
        if key in catalog:
            text = catalog[key]
            try:
                return text.format(**params) if params else text
            except (KeyError, IndexError):
                return text
    return key


def catalog_keys(locale: str) -> frozenset[str]:
    return frozenset(_catalog(locale))
