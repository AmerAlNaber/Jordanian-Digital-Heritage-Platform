"""Identity shapes. A user is identified by the identity provider's subject, never a row id."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from jdhp_api.core.orm import UserRole, UserVerification


class InstitutionRef(BaseModel):
    slug: str
    name_ar: str
    name_en: str | None


class Me(BaseModel):
    subject: str
    email: str | None
    display_name: str | None
    role: UserRole
    verification_level: UserVerification
    institution: InstitutionRef | None
    preferences: dict[str, Any]
    mfa: bool


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str | None = Field(default=None, pattern="^(ar|en)$")
    numerals: str | None = Field(default=None, pattern="^(eastern|western)$")
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")
