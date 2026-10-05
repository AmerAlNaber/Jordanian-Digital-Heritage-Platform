"""SEC-6: every route in the public application calls the policy engine. Zero exemptions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from jdhp_api.core.authz import Authorize


def _has_authorize(dependant: Dependant) -> bool:
    if isinstance(dependant.call, Authorize):
        return True
    return any(_has_authorize(sub) for sub in dependant.dependencies)


def _walk(routes: Iterable[Any]) -> Iterator[APIRoute]:
    """FastAPI may hold included routers as wrappers; descend into anything that has routes."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        nested = getattr(route, "routes", None)
        if nested is None:
            inner = getattr(route, "original_router", None) or getattr(route, "router", None)
            nested = getattr(inner, "routes", None)
        if nested is not None:
            yield from _walk(nested)


def api_routes(app: FastAPI) -> list[APIRoute]:
    return list(_walk(app.routes))


def test_sec_6_every_route_calls_policy_engine(app: FastAPI) -> None:
    unprotected = [
        f"{','.join(sorted(route.methods or []))} {route.path}"
        for route in api_routes(app)
        if not _has_authorize(route.dependant)
    ]
    assert unprotected == [], f"routes without an Authorize dependency: {unprotected}"


def test_sec_6_public_app_has_routes_to_protect(app: FastAPI) -> None:
    assert len(api_routes(app)) >= 15


def test_sec_6_health_endpoints_are_not_in_the_public_app(app: FastAPI) -> None:
    paths = {route.path for route in api_routes(app)}
    assert not paths & {"/healthz", "/readyz", "/metrics"}
