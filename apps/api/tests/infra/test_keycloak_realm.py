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
    # A composite grants its children, so every staff role must include ``staff``; the
    # reverse shape (``staff`` listing the staff roles) never made a curator hold ``staff``.
    by_name = {role["name"]: role for role in realm["roles"]["realm"]}
    assert "composites" not in by_name["staff"]
    for name in STAFF_ROLES:
        assert by_name[name]["composites"]["realm"] == ["staff"], name
    default = next(r for r in realm["roles"]["realm"] if r["name"] == realm["defaultRole"]["name"])
    assert "member" in default["composites"]["realm"]


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


def test_sec_1_clients_reference_only_scopes_the_realm_defines(realm: dict[str, Any]) -> None:
    """A realm that lists client scopes gets none of Keycloak's built-ins, so they are listed."""
    defined = {scope["name"] for scope in realm["clientScopes"]}
    assert {"basic", "profile", "email", "roles", "web-origins", "acr", "jdhp-audience"} <= defined
    for client in realm["clients"]:
        wanted = set(client.get("defaultClientScopes", [])) | set(
            client.get("optionalClientScopes", [])
        )
        assert wanted <= defined, (client["clientId"], wanted - defined)
        if client["clientId"] in {"jdhp-web", "jdhp-staff"}:
            assert {"profile", "email", "roles", "basic"} <= set(client["defaultClientScopes"])
    roles_scope = next(s for s in realm["clientScopes"] if s["name"] == "roles")
    assert "oidc-usermodel-realm-role-mapper" in {
        m["protocolMapper"] for m in roles_scope["protocolMappers"]
    }, "realm_access.roles is what the API reads"


def test_sec_2_realm_token_lifetimes(realm: dict[str, Any]) -> None:
    assert realm["accessTokenLifespan"] == 600
    assert realm["ssoSessionIdleTimeout"] == 28800
    assert realm["ssoSessionMaxLifespan"] <= 28800
    assert realm["revokeRefreshToken"] is True
    assert realm["refreshTokenMaxReuse"] == 0
    staff = next(c for c in realm["clients"] if c["clientId"] == "jdhp-staff")
    assert staff["attributes"]["client.session.idle.timeout"] == "3600"
    assert staff["attributes"]["client.session.max.lifespan"] == "3600"


def executions(realm: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    return list(flows(realm)[alias]["authenticationExecutions"])


def names(items: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("authenticator") or e.get("flowAlias")) for e in items]


def condition_role(realm: dict[str, Any], execution: dict[str, Any]) -> tuple[str, bool]:
    config = configs(realm)[execution["authenticatorConfig"]]
    # Keycloak 26 reads the role from ``condUserRole``; the old key is silently ignored and the
    # condition then disables its whole sub-flow, which is how Phase 0 lost staff MFA.
    assert "condUserRole" in config, config
    return config["condUserRole"], config.get("negate") == "true"


def test_sec_3_mfa_required_for_every_staff_role(realm: dict[str, Any]) -> None:
    assert realm["browserFlow"] == "jdhp browser"
    forms = executions(realm, "jdhp forms")
    assert names(forms) == [
        "auth-username-form",
        "jdhp credentials",
        "jdhp second factor",
        "jdhp staff code",
        "jdhp admin webauthn",
    ]
    assert [e["requirement"] for e in forms] == [
        "REQUIRED",
        "REQUIRED",
        "CONDITIONAL",
        "CONDITIONAL",
        "CONDITIONAL",
    ]
    staff = executions(realm, "jdhp staff code")
    assert names(staff) == ["conditional-user-role", "conditional-credential", "auth-otp-form"]
    assert all(e["requirement"] == "REQUIRED" for e in staff)
    assert condition_role(realm, staff[0]) == ("staff", False)
    # "no code presented yet in this sign-in": enrol or enter one, but never ask twice.
    assert configs(realm)[staff[1]["authenticatorConfig"]] == {
        "credentials": "otp",
        "included": "false",
    }


def test_sec_3_platform_admin_requires_webauthn(realm: dict[str, Any]) -> None:
    admin_flow = executions(realm, "jdhp admin webauthn")
    assert names(admin_flow) == ["conditional-user-role", "webauthn-authenticator"]
    assert condition_role(realm, admin_flow[0]) == ("platform_admin", False)
    assert admin_flow[1]["requirement"] == "REQUIRED"
    assert realm["webAuthnPolicyUserVerificationRequirement"] == "required"
    assert realm["webAuthnPolicyAuthenticatorAttachment"] == "cross-platform"


def test_acc_1_a_credential_is_required_before_any_condition_runs(realm: dict[str, Any]) -> None:
    """A misconfigured condition disables its sub-flow; the credential step must not sit in one."""
    forms = executions(realm, "jdhp forms")
    credentials = next(e for e in forms if e.get("flowAlias") == "jdhp credentials")
    assert credentials["requirement"] == "REQUIRED"
    assert flows(realm)["jdhp credentials"]["authenticationExecutions"], "never empty"
    assert names(executions(realm, "jdhp credentials")) == [
        "webauthn-authenticator-passwordless",
        "auth-password-form",
    ]
    assert all(e["requirement"] == "ALTERNATIVE" for e in executions(realm, "jdhp credentials"))


def test_acc_1_members_may_sign_in_with_a_passkey(realm: dict[str, Any]) -> None:
    # A passkey is a resident, user-verified credential on any authenticator the member owns.
    assert realm["webAuthnPolicyPasswordlessRequireResidentKey"] == "Yes"
    assert realm["webAuthnPolicyPasswordlessUserVerificationRequirement"] == "required"
    assert realm["webAuthnPolicyPasswordlessAuthenticatorAttachment"] == "not specified"
    enrol = next(
        a for a in realm["requiredActions"] if a["alias"] == "webauthn-register-passwordless"
    )
    assert enrol["enabled"] is True
    assert enrol["defaultAction"] is False


def test_acc_2_members_who_enrolled_a_code_must_use_it(realm: dict[str, Any]) -> None:
    second = executions(realm, "jdhp second factor")
    assert names(second) == ["conditional-user-configured", "auth-otp-form"]
    assert all(e["requirement"] == "REQUIRED" for e in second)
    totp = next(a for a in realm["requiredActions"] if a["alias"] == "CONFIGURE_TOTP")
    assert totp["enabled"] is True


def test_sec_3_every_credential_step_reports_its_method(realm: dict[str, Any]) -> None:
    """The API derives ``mfa`` from the amr claim, so each step must carry a reference value."""
    expected = {
        "webauthn-authenticator-passwordless": "swk",
        "auth-password-form": "pwd",
        "auth-otp-form": "otp",
        "webauthn-authenticator": "hwk",
    }
    seen: dict[str, set[str]] = {}
    for flow in realm["authenticationFlows"]:
        for e in flow["authenticationExecutions"]:
            if e.get("authenticator") in expected:
                config = configs(realm)[e["authenticatorConfig"]]
                seen.setdefault(e["authenticator"], set()).add(config["default.reference.value"])
                assert int(config["default.reference.maxAge"]) >= realm["ssoSessionMaxLifespan"]
    assert {k: {v} for k, v in expected.items()} == seen


def test_realm_default_role_grants_member(realm: dict[str, Any]) -> None:
    default = next(r for r in realm["roles"]["realm"] if r["name"] == "default-roles-jdhp")
    assert "member" in default["composites"]["realm"]
    assert realm["defaultRole"]["name"] == "default-roles-jdhp"


def test_acc_1_registration_verifies_email(realm: dict[str, Any]) -> None:
    assert realm["registrationAllowed"] is True
    assert realm["registrationEmailAsUsername"] is True
    assert realm["verifyEmail"] is True
    verify = next(a for a in realm["requiredActions"] if a["alias"] == "VERIFY_EMAIL")
    assert verify["enabled"] is True
    assert verify["defaultAction"] is True


def test_sec_4_breached_password_policy_configured(realm: dict[str, Any]) -> None:
    """The check itself is proven by infra/keycloak/extensions tests; the realm must turn it on."""
    assert "breachedPassword(0)" in realm["passwordPolicy"]


def test_sec_5_member_tokens_carry_the_account_audience(realm: dict[str, Any]) -> None:
    scope = next(s for s in realm["clientScopes"] if s["name"] == "jdhp-audience")
    audiences = {
        m["config"]["included.client.audience"]
        for m in scope["protocolMappers"]
        if m["protocolMapper"] == "oidc-audience-mapper"
    }
    assert audiences == {"jdhp-api", "account"}


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


def test_sec_1_frontend_url_carries_the_relative_path(realm: dict[str, Any]) -> None:
    """Keycloak is served under /auth behind Caddy; every URL it renders must say so."""
    assert realm["attributes"]["frontendUrl"].endswith("/auth")


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
