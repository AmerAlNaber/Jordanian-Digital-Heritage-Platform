"""Authorization: every route asks the policy engine (SEC-6).

``Authorize`` is a FastAPI dependency. It loads the resource by its public identifier, builds
the Cerbos principal and resource, asks for a decision, records the decision in the audit log
in its own transaction so a denial survives the request rollback, and raises on deny. A policy
engine failure is a denial. The route-coverage test recognises routes by this dependency, so
a handler without it fails CI.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx
from cerbos.sdk.client import AsyncCerbosClient
from cerbos.sdk.model import Principal as CerbosPrincipal
from cerbos.sdk.model import Resource as CerbosResource
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal, get_principal
from jdhp_api.core.config import Settings, get_settings
from jdhp_api.core.db import Database
from jdhp_api.core.deps import get_database, get_session
from jdhp_api.core.errors import ForbiddenError, NotFoundError, PolicyEngineUnavailableError
from jdhp_api.core.observability import get_logger

log = get_logger(__name__)

# Cerbos treats "*" specially, so kind-level checks use a plain placeholder id.
KIND_LEVEL_ID = "any"


@dataclasses.dataclass(frozen=True, slots=True)
class ResourceRef:
    """What the policy engine sees: kind, opaque id and the attributes the policies read."""

    kind: str
    id: str
    attr: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def for_kind(cls, kind: str) -> ResourceRef:
        """Kind-level actions such as listing or creating, with no single resource."""
        return cls(kind=kind, id=KIND_LEVEL_ID, attr={})


Loader = Callable[[Request, AsyncSession, Principal], Awaitable[tuple[Any, ResourceRef]]]


class PolicyClient(Protocol):
    async def is_allowed(
        self, principal: Principal, action: str, resource: ResourceRef, request_id: str | None
    ) -> bool: ...

    async def healthy(self) -> bool: ...


class CerbosPolicyClient:
    """Cerbos over HTTP. Any transport or server error becomes a denial."""

    def __init__(self, settings: Settings) -> None:
        self._host = str(settings.cerbos_url).rstrip("/")
        self._client = AsyncCerbosClient(self._host, timeout_secs=2.0, raise_on_error=True)

    async def is_allowed(
        self, principal: Principal, action: str, resource: ResourceRef, request_id: str | None
    ) -> bool:
        cerbos_principal = CerbosPrincipal(
            id=principal.id, roles=set(principal.roles), attr=principal.cerbos_attributes()
        )
        cerbos_resource = CerbosResource(
            id=resource.id, kind=resource.kind, attr=dict(resource.attr)
        )
        try:
            return bool(
                await self._client.is_allowed(
                    action, cerbos_principal, cerbos_resource, request_id=request_id
                )
            )
        except Exception as exc:
            log.error("policy_engine_error", error=str(exc), action=action, kind=resource.kind)
            raise PolicyEngineUnavailableError from exc

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as http:
                response = await http.get(f"{self._host}/_cerbos/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200


def get_policy_client(request: Request) -> PolicyClient:
    client = getattr(request.app.state, "policy_client", None)
    if client is None:
        client = CerbosPolicyClient(get_settings())
        request.app.state.policy_client = client
    return client


@dataclasses.dataclass(slots=True)
class Authorized:
    """What a handler receives: the principal, the request's session and the loaded resource."""

    principal: Principal
    session: AsyncSession
    resource: Any
    ref: ResourceRef
    request_id: str | None
    action: str


class Authorize:
    """Dependency factory: ``Depends(Authorize("read", "work", load_work))``."""

    def __init__(
        self,
        action: str,
        kind: str,
        loader: Loader | None = None,
        *,
        hide_existence: bool = False,
    ) -> None:
        self.action = action
        self.kind = kind
        self.loader = loader
        self.hide_existence = hide_existence
        self.__name__ = f"authorize_{action}_{kind}"

    async def __call__(
        self,
        request: Request,
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
        policy: PolicyClient = Depends(get_policy_client),
        database: Database = Depends(get_database),
    ) -> Authorized:
        request_id = getattr(request.state, "request_id", None)
        if self.loader is not None:
            resource, ref = await self.loader(request, session, principal)
        else:
            resource, ref = None, ResourceRef.for_kind(self.kind)
        allowed = await policy.is_allowed(principal, self.action, ref, request_id)
        await audit.record_decision(
            database,
            principal=principal,
            action=self.action,
            ref=ref,
            allowed=allowed,
            request=request,
        )
        if not allowed:
            if self.hide_existence:
                raise NotFoundError
            raise ForbiddenError
        return Authorized(
            principal=principal,
            session=session,
            resource=resource,
            ref=ref,
            request_id=request_id,
            action=self.action,
        )
