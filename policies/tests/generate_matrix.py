"""Generate the exhaustive work-policy test matrix from the access table in SPEC.md.

Run: ``python policies/tests/generate_matrix.py`` and commit the result. The expectations are
written as code so that the specification's table, not the policy files, is the oracle.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import yaml

STAFF = {"curator", "reviewer", "rights_officer", "platform_admin"}
ROLES = [
    "anonymous",
    "member",
    "verified_researcher",
    "institutional_user",
    "institution_admin",
    "curator",
    "reviewer",
    "rights_officer",
    "platform_admin",
]
CLASSES = ["open", "registered", "paid", "restricted", "embargoed"]
ACTIONS = ["view", "read", "print", "request_access"]


def principal(role: str) -> dict:
    authenticated = role != "anonymous"
    return {
        "id": role,
        "roles": [role],
        "attr": {
            "authenticated": authenticated,
            "verification_level": "researcher" if role == "verified_researcher" else ("phone" if authenticated else "none"),
            "institution_id": "inst-1" if role.startswith("institution") else "",
            "mfa": role in STAFF,
            "session_age_seconds": 0,
            "active_devices": 1 if authenticated else 0,
            "is_staff": role in STAFF,
        },
    }


def resource(access_class: str, published: bool, has_grant: bool, frozen: bool) -> tuple[str, dict]:
    name = f"{access_class}_{'pub' if published else 'draft'}_{'grant' if has_grant else 'nogrant'}{'_frozen' if frozen else ''}"
    return name, {
        "kind": "work",
        "id": name,
        "attr": {
            "access_class": access_class,
            "publish_state": "published" if published else "draft",
            "frozen": frozen,
            "has_grant": has_grant,
            "grant_page_from": None,
            "grant_page_to": None,
            "owner_institution_id": "",
            "break_glass_active": False,
        },
    }


def expected(role: str, access_class: str, published: bool, has_grant: bool, frozen: bool, action: str) -> bool:
    """The access class table of SPEC.md, read literally."""
    authenticated = role != "anonymous"
    staff = role in STAFF
    content_staff = staff and role != "platform_admin"  # admins have no content bypass (SEC-8)
    visible = published and access_class != "embargoed" and not frozen
    if action == "view":
        return staff or visible
    if action == "read":
        if frozen:
            return False
        if content_staff:
            return access_class != "embargoed"
        if not published:
            return False
        if access_class == "open":
            return True
        if access_class == "registered":
            return authenticated
        if access_class in {"paid", "restricted"}:
            return authenticated and has_grant
        return False
    if action == "print":
        if access_class in {"restricted", "embargoed"} or not published:
            return False
        if access_class == "open":
            return True
        if access_class == "registered":
            return authenticated
        return authenticated and has_grant  # paid
    if action == "request_access":
        return authenticated and published and access_class == "restricted"
    raise ValueError(action)


def build() -> dict:
    principals = {role: principal(role) for role in ROLES}
    resources: dict[str, dict] = {}
    combos = []
    for access_class, published, has_grant in itertools.product(CLASSES, [True, False], [False, True]):
        name, res = resource(access_class, published, has_grant, frozen=False)
        resources[name] = res
        combos.append((name, access_class, published, has_grant, False))
    name, res = resource("registered", True, False, frozen=True)
    resources[name] = res
    combos.append((name, "registered", True, False, True))

    tests = []
    for role in ROLES:
        expectations = []
        for name, access_class, published, has_grant, frozen in combos:
            if has_grant and role == "anonymous":
                continue  # anonymous visitors never hold a grant
            expectations.append(
                {
                    "principal": role,
                    "resource": name,
                    "actions": {
                        action: "EFFECT_ALLOW" if expected(role, access_class, published, has_grant, frozen, action) else "EFFECT_DENY"
                        for action in ACTIONS
                    },
                }
            )
        tests.append(
            {
                "name": f"{role} across every access class",
                "input": {
                    "principals": [role],
                    "resources": [e["resource"] for e in expectations],
                    "actions": ACTIONS,
                },
                "expected": expectations,
            }
        )
    return {
        "name": "WorkAccessMatrix",
        "description": "Every role against every access class, publish state and grant state (SPEC.md access table). Generated by generate_matrix.py.",
        "principals": principals,
        "resources": resources,
        "tests": tests,
    }


if __name__ == "__main__":
    out = Path(__file__).with_name("work_matrix_test.yaml")
    out.write_text("# Generated by generate_matrix.py. Do not edit by hand.\n" + yaml.safe_dump(build(), sort_keys=False, allow_unicode=True, width=120))
    print(f"wrote {out}")
