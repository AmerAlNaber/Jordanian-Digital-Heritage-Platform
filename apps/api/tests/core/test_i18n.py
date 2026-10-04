"""INT-1: API messages are externalized in Arabic and English, Arabic by default."""

from __future__ import annotations

from jdhp_api.core.i18n import catalog_keys, negotiate_locale, translate


def test_arabic_is_the_default_locale() -> None:
    assert negotiate_locale(None) == "ar"
    assert negotiate_locale("") == "ar"
    assert negotiate_locale("fr-FR, de;q=0.8") == "ar"
    assert negotiate_locale("*") == "ar"


def test_quality_values_are_honoured() -> None:
    assert negotiate_locale("en;q=0.5, ar;q=0.9") == "ar"
    assert negotiate_locale("ar;q=0.5, en-GB;q=0.9") == "en"
    assert negotiate_locale("en-US,en;q=0.9,ar;q=0.8") == "en"


def test_catalogs_have_identical_keys() -> None:
    assert catalog_keys("ar") == catalog_keys("en")
    assert catalog_keys("ar")


def test_translate_falls_back_to_default_locale_then_key() -> None:
    assert translate("en", "errors.not_found.title") == "Not found"
    assert translate("ar", "errors.not_found.title") == "غير موجود"
    assert translate("en", "missing.key") == "missing.key"
