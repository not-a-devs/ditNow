"""Disabled authentication/authorization seams. No live protected routes use these yet."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request
from pydantic import ConfigDict

from app.core.errors import ApiError
from app.schemas.common import ApiModel, ErrorCode


class VerifiedPrincipal(ApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    user_id: UUID
    active: bool


class IdentityProvider(Protocol):
    async def verify(self, request: Request) -> VerifiedPrincipal: ...


class AuthorizationPolicy(Protocol):
    async def require(
        self, principal: VerifiedPrincipal, action: str, resource_id: UUID | None
    ) -> None: ...


def get_identity_provider() -> IdentityProvider:
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_authorization_policy() -> AuthorizationPolicy:
    raise ApiError(ErrorCode.UNAVAILABLE)


async def require_principal(
    request: Request, provider: Annotated[IdentityProvider, Depends(get_identity_provider)]
) -> VerifiedPrincipal:
    principal = await provider.verify(request)
    if not principal.active:
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return principal


def authorize(action: str, resource_parameter: str | None = None):
    async def dependency(
        request: Request,
        principal: Annotated[VerifiedPrincipal, Depends(require_principal)],
        policy: Annotated[AuthorizationPolicy, Depends(get_authorization_policy)],
    ) -> VerifiedPrincipal:
        resource_id = None
        if resource_parameter is not None:
            value = request.path_params.get(resource_parameter)
            if value is None:
                raise ApiError(ErrorCode.UNAVAILABLE)
            try:
                resource_id = UUID(str(value))
            except ValueError:
                raise ApiError(ErrorCode.VALIDATION) from None
        # Implementations must re-read current membership, scope, owner and state, not token claims.
        await policy.require(principal, action, resource_id)
        return principal

    return dependency
