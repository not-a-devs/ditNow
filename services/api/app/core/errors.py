from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorCode, ErrorResponse

ERRORS: dict[ErrorCode, tuple[int, str, bool]] = {
    ErrorCode.VALIDATION: (400, "입력값을 확인하세요.", False),
    ErrorCode.UNAUTHORIZED: (401, "인증이 필요합니다.", False),
    ErrorCode.FORBIDDEN: (403, "접근할 수 없습니다.", False),
    ErrorCode.NOT_FOUND: (404, "요청한 자원을 찾을 수 없습니다.", False),
    ErrorCode.CONFLICT: (409, "현재 상태와 충돌합니다.", False),
    ErrorCode.RATE_LIMITED: (429, "잠시 후 다시 시도하세요.", True),
    ErrorCode.UNAVAILABLE: (503, "서비스를 사용할 수 없습니다.", True),
    ErrorCode.INTERNAL: (500, "요청을 처리하지 못했습니다.", True),
    ErrorCode.HTTP_ERROR: (400, "요청을 처리할 수 없습니다.", False),
}


class ApiError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code.value)


def error_response(
    code: ErrorCode,
    request_id: str,
    *,
    status_code: int | None = None,
    field_errors: dict[str, str] | None = None,
) -> JSONResponse:
    status, message, retryable = ERRORS[code]
    body = ErrorResponse(
        code=code,
        message=message,
        field_errors=field_errors,
        retryable=retryable,
        request_id=request_id,
    )
    return JSONResponse(
        body.model_dump(mode="json"),
        status_code=status_code or status,
        headers={"X-Request-ID": request_id},
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.code, request.state.request_id)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Raw Pydantic input/context and arbitrary nested keys can contain credentials or PII.
    locations = {
        str(error["loc"][0]): "입력값이 올바르지 않습니다."
        for error in exc.errors()
        if error["loc"] and error["loc"][0] in {"body", "query", "path", "header", "cookie"}
    }
    return error_response(ErrorCode.VALIDATION, request.state.request_id, field_errors=locations)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = next((key for key, value in ERRORS.items() if value[0] == exc.status_code), None)
    response = error_response(
        code or ErrorCode.HTTP_ERROR, request.state.request_id, status_code=exc.status_code
    )
    if exc.status_code == 405 and exc.headers:
        methods = exc.headers.get("Allow", "").split(", ")
        if methods and all(
            method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            for method in methods
        ):
            response.headers["Allow"] = ", ".join(methods)
    return response
