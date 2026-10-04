"""Public identifiers are opaque ARK names with a check character (ADR-0001 D10, INT-7)."""

from __future__ import annotations

import uuid

import pytest

from jdhp_api.core import ids


def test_uuid7_is_time_ordered_and_version_7() -> None:
    first, second = ids.uuid7(), ids.uuid7()
    assert isinstance(first, uuid.UUID)
    assert first.version == 7
    assert first < second


def test_minted_name_has_shoulder_and_valid_check_character() -> None:
    name = ids.mint_name("w8")
    assert name.startswith("w8")
    assert len(name) == 2 + ids.NOID_BODY_LENGTH + 1
    assert ids.is_valid_name(name)


def test_names_are_unique_and_never_sequential() -> None:
    names = {ids.mint_name("w8") for _ in range(500)}
    assert len(names) == 500


@pytest.mark.parametrize("mutation", ["swap", "replace", "truncate", "uppercase"])
def test_mutated_name_fails_the_check(mutation: str) -> None:
    name = ids.mint_name("w8")
    body = name[:-1]
    if mutation == "swap":
        candidate = body[:3] + body[4] + body[3] + body[5:] + name[-1]
        if candidate == name:  # the two characters were equal; pick another pair
            candidate = body[:5] + body[6] + body[5] + body[7:] + name[-1]
            if candidate == name:
                pytest.skip("name has repeated characters at both probe positions")
    elif mutation == "replace":
        new_char = "b" if body[5] != "b" else "c"
        candidate = body[:5] + new_char + body[6:] + name[-1]
    elif mutation == "truncate":
        candidate = name[:-1]
    else:
        candidate = name.upper()
    assert not ids.is_valid_name(candidate)


def test_noid_check_character_matches_the_published_algorithm() -> None:
    # Positions start at 1, ordinals from the extended-digit alphabet, modulo 29.
    body = "w8" + "0123456789"
    expected_total = sum(
        pos * ids.NOID_ALPHABET.find(c) if c in ids.NOID_ALPHABET else 0
        for pos, c in enumerate(body, 1)
    )
    assert ids.noid_check_char(body) == ids.NOID_ALPHABET[expected_total % 29]


def test_ark_formatting_and_page_qualifiers() -> None:
    assert ids.format_ark("99999", "w8abc") == "ark:/99999/w8abc"
    assert ids.format_page_ark("99999", "w8abc", 7) == "ark:/99999/w8abc/p7"
    assert ids.parse_page_qualifier("p12") == 12
    assert ids.parse_page_qualifier("p0") is None
    assert ids.parse_page_qualifier("12") is None
    with pytest.raises(ValueError, match="start at 1"):
        ids.page_qualifier(0)
