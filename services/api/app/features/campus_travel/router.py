from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from app.core.errors import (
    ApiError,
    api_error_handler,
    error_response,
    http_error_handler,
    validation_error_handler,
)
from app.features.campus_travel.models import TravelInput, TravelResult
from app.features.campus_travel.service import calculate_travel
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class TravelRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await original(request)
            except ApiError as exc:
                response = await api_error_handler(request, exc)
            except RequestValidationError as exc:
                response = await validation_error_handler(request, exc)
            except HTTPException as exc:
                response = await http_error_handler(request, exc)
            except Exception:
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


def build_travel_router(*, enabled: bool = False) -> APIRouter:
    router = APIRouter(
        prefix="/campus-travel",
        tags=["campus-travel-manual"],
        route_class=TravelRoute,
        responses={s: {"model": ErrorResponse} for s in (400, 500, 503)},
    )

    @router.post("/calculate", response_model=SuccessResponse[TravelResult])
    def calculate(value: TravelInput):
        if not enabled:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return SuccessResponse(data=calculate_travel(value))

    return router


router = build_travel_router()
