"""Identifiers: UUIDv7 primary keys and ARK public identifiers (ADR-0001 D10).

Internal identifiers never leave the server. Public identifiers are opaque NOID-style
names under a configurable Name Assigning Authority Number, with a check character so a
mistyped identifier is detected before any lookup. Pages are qualified under their work.
"""

from __future__ import annotations

import re
import secrets
import uuid

import uuid_utils

# The 29 NOID "extended digits": digits plus consonants, no vowels, so names never spell words.
NOID_ALPHABET = "0123456789bcdfghjkmnpqrstvwxz"
NOID_BODY_LENGTH = 10
_NAME_PATTERN = re.compile(rf"^[a-z]+[0-9][{NOID_ALPHABET}]{{{NOID_BODY_LENGTH + 1}}}$")
_PAGE_QUALIFIER = re.compile(r"^p(?P<seq>[1-9][0-9]*)$")


def uuid7() -> uuid.UUID:
    """Time-ordered UUID for every primary key."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def _ordinal(char: str) -> int:
    index = NOID_ALPHABET.find(char)
    return index if index >= 0 else 0


def noid_check_char(body: str) -> str:
    """NOID check character: alphabet[sum(position * ordinal) mod 29], positions from 1."""
    total = sum(position * _ordinal(char) for position, char in enumerate(body, start=1))
    return NOID_ALPHABET[total % len(NOID_ALPHABET)]


def mint_name(shoulder: str) -> str:
    """A new opaque public name: shoulder, ten random extended digits, one check character."""
    number = secrets.randbelow(len(NOID_ALPHABET) ** NOID_BODY_LENGTH)
    digits: list[str] = []
    for _ in range(NOID_BODY_LENGTH):
        number, remainder = divmod(number, len(NOID_ALPHABET))
        digits.append(NOID_ALPHABET[remainder])
    body = shoulder + "".join(digits)
    return body + noid_check_char(body)


def is_valid_name(name: str) -> bool:
    """Shape and check character. Cheap enough to run before every lookup."""
    if not _NAME_PATTERN.match(name):
        return False
    return noid_check_char(name[:-1]) == name[-1]


def format_ark(naan: str, name: str) -> str:
    return f"ark:/{naan}/{name}"


def page_qualifier(seq: int) -> str:
    if seq < 1:
        msg = "page sequence numbers start at 1"
        raise ValueError(msg)
    return f"p{seq}"


def format_page_ark(naan: str, name: str, seq: int) -> str:
    return f"{format_ark(naan, name)}/{page_qualifier(seq)}"


def parse_page_qualifier(qualifier: str) -> int | None:
    match = _PAGE_QUALIFIER.match(qualifier)
    return int(match.group("seq")) if match else None
