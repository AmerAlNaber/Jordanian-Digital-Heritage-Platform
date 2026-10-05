"""Identity shapes. A user is identified by the identity provider's subject, never a row id."""

from __future__ import annotations

import datetime as dt
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
    phone_number: str | None = Field(
        default=None, description="Masked: only the last two digits show"
    )
    phone_verified_at: dt.datetime | None = None


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str | None = Field(default=None, pattern="^(ar|en)$")
    numerals: str | None = Field(default=None, pattern="^(eastern|western)$")
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")


E164 = r"^\+[1-9]\d{7,14}$"


class PhoneStart(BaseModel):
    """Ask for a verification code at a number in E.164 form (ACC-1)."""

    model_config = ConfigDict(extra="forbid")

    phone_number: str = Field(pattern=E164, examples=["+962790001234"])


class PhoneConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")


class PhoneStatus(BaseModel):
    phone_number: str | None = Field(default=None, description="Masked")
    verified_at: dt.datetime | None
    pending: bool = Field(description="A code is out and still valid")
    expires_at: dt.datetime | None


class ReaderSessionSummary(BaseModel):
    """One open reader of the signed-in user, as the account page lists it (SEC-5)."""

    public_id: str
    work: str
    title_ar: str
    title_en: str | None
    device: str = Field(description="First eight characters of the device hash")
    sign_in: str | None = Field(
        description="The identity provider's session the reader was opened under"
    )
    current_sign_in: bool
    started_at: dt.datetime
    last_seen_at: dt.datetime
    idle_expires_at: dt.datetime


class SessionsOut(BaseModel):
    sign_in: str | None = Field(description="This request's sign-in session")
    readers: list[ReaderSessionSummary]
