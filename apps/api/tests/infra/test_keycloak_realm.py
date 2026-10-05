"""The realm of record encodes SEC-1 to SEC-4 and ACC-1. These tests read the template as data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REALM_PATH = Path(__file__).resolve().parents[4] / "infra" / "keycloak" / "realm-jdhp.template.json"
STAFF_ROLES = {"curator", "reviewer", "rights_officer", "platform_admin"}
ALL_ROLES = STAFF_ROLES | {
    "member",
    "verified_researcher",
    "institutional_user",
    "institution_admin",
}


@pytest.fixture(scope="module")
def realm() -> dict[str, Any]:
    text = REALM_PATH.read_text("utf-8")
    # Placeholders are rendered by infra/compose/keycloak/render-realm.py before import;
    # substitute harmless values here.
    rendered = re.sub(r"\$\{([A-Z_]+)\}", lambda m: f"placeholder-{m.group(1).lower()}", text)
    data = json.loads(rendered)
    assert isinstance(data, dict)
    return data


def flows(realm: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {flow["alias"]: flow for flow in realm["authenticationFlows"]}


def configs(realm: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {c["alias"]: c["config"] for c in realm["authenticatorConfig"]}


def test_realm_roles_match_the_specification(realm: dict[str, Any]) -> None:
    names = {role["name"] for role in realm["roles"]["realm"]}
    assert names >= ALL_ROLES
    staff = next(role for role in realm["roles"]["realm"] if role["name"] == "staff")
    assert set(staff["composites"]["realm"]) == STAFF_ROLES
    assert "member" in realm["defaultRole"]["composites"]["realm"]


def test_sec_1_code_flow_with_pkce_only(realm: dict[str, Any]) -> None:
    web_clients = [c for c in realm["clients"] if c["clientId"] in {"jdhp-web", "jdhp-staff"}]
    assert len(web_clients) == 2
    for client in web_clients:
        assert client["standardFlowEnabled"] is True
        assert client["implicitFlowEnabled"] is False
        assert client["directAccessGrantsEnabled"] is False, "the API never sees a password"
        assert client["publicClient"] is False
        assert client["attributes"]["pkce.code.challenge.method"] == "S256"
        assert "jdhp-audience" in client["defaultClientScopes"]
    api = next(c for c in realm["clients"] if c["clientId"] == "jdhp-api")
    assert api["bearerOnly"] is True


def test_sec_2_realm_token_lifetimes(realm: dict[str, Any]) -> None:
    assert realm["accessTokenLifespan"] == 600
    assert realm["ssoSessionIdleTimeout"] == 28800
    assert realm["ssoSessionMaxLifespan"] <= 28800
    assert realm["revokeRefreshToken"] is True
    assert realm["refreshTokenMaxReuse"] == 0
    staff = next(c for c in realm["clients"] if c["clientId"] == "jdhp-staff")
    assert staff["attributes"]["client.session.idle.timeout"] == "3600"
    assert staff["attributes"]["client.session.max.lifespan"] == "3600"


def test_sec_3_mfa_required_for_every_staff_role(realm: dict[str, Any]) -> None:
    assert realm["browserFlow"] == "jdhp browser"
    forms = flows(realm)["jdhp forms"]
    sub_flows = {
        e["flowAlias"]: e["requirement"]
        for e in forms["authenticationExecutions"]
        if e.get("flowAlias")
    }
    assert sub_flows["jdhp staff otp"] == "CONDITIONAL"
    staff_otp = flows(realm)["jdhp staff otp"]
    executions = staff_otp["authenticationExecutions"]
    condition = next(e for e in executions if e["authenticator"] == "conditional-user-role")
    assert configs(realm)[condition["authenticatorConfig"]]["condition.user.role"] == "staff"
    otp = next(e for e in executions if e["authenticator"] == "auth-otp-form")
    assert otp["requirement"] == "REQUIRED"


def test_sec_3_platform_admin_requires_webauthn(realm: dict[str, Any]) -> None:
    admin_flow = flows(realm)["jdhp admin webauthn"]
    executions = admin_flow["authenticationExecutions"]
    condition = next(e for e in executions if e["authenticator"] == "conditional-user-role")
    assert (
        configs(realm)[condition["authenticatorConfig"]]["condition.user.role"] == "platform_admin"
    )
    webauthn = next(e for e in executions if e["authenticator"] == "webauthn-authenticator")
    assert webauthn["requirement"] == "REQUIRED"
    assert realm["webAuthnPolicyUserVerificationRequirement"] == "required"
    assert realm["webAuthnPolicyAuthenticatorAttachment"] == "cross-platform"


def test_sec_4_lockout_after_ten_failures(realm: dict[str, Any]) -> None:
    assert realm["bruteForceProtected"] is True
    assert realm["failureFactor"] == 10
    assert realm["waitIncrementSeconds"] >= 60
    assert realm["maxFailureWaitSeconds"] >= 900


def test_acc_1_password_policy_prefers_length(realm: dict[str, Any]) -> None:
    policy = realm["passwordPolicy"]
    assert "length(12)" in policy
    assert "digits(" not in policy
    assert "specialChars(" not in policy
    assert "upperCase(" not in policy


def test_int_1_arabic_is_the_default_locale(realm: dict[str, Any]) -> None:
    assert realm["internationalizationEnabled"] is True
    assert realm["defaultLocale"] == "ar"
    assert set(realm["supportedLocales"]) == {"ar", "en"}


def test_claims_the_api_reads_are_mapped(realm: dict[str, Any]) -> None:
    scope = next(s for s in realm["clientScopes"] if s["name"] == "jdhp-audience")
    mappers = {m["protocolMapper"] for m in scope["protocolMappers"]}
    assert {"oidc-audience-mapper", "oidc-amr-mapper", "oidc-acr-mapper"} <= mappers
    audience = next(
        m for m in scope["protocolMappers"] if m["protocolMapper"] == "oidc-audience-mapper"
    )
    assert audience["config"]["included.client.audience"] == "jdhp-api"
