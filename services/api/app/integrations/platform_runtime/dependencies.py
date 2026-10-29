from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.api.v1.auth import Credentials, client_ip
from app.core.errors import ApiError
from app.integrations.platform_runtime.bindings import BoundSession
from app.integrations.platform_runtime.runtime import PlatformRuntime
from app.schemas.common import ErrorCode


def get_runtime(request: Request) -> PlatformRuntime:
    runtime = request.app.state.platform_runtime
    if runtime is None:
        raise ApiError(ErrorCode.UNAVAILABLE)
    request.app.state.assistant.check_rate_limit(client_ip(request))
    return runtime


Runtime = Annotated[PlatformRuntime, Depends(get_runtime)]


@dataclass(frozen=True)
class RequestContext:
    runtime: PlatformRuntime
    token: str
    binding: BoundSession


async def get_context(request: Request, creds: Credentials, runtime: Runtime) -> RequestContext:
    token = creds.credentials if creds else None
    binding = await runtime.context(token)
    return RequestContext(runtime, token or "", binding)


Context = Annotated[RequestContext, Depends(get_context)]
