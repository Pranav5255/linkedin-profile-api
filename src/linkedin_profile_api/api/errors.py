from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from linkedin_profile_api.api.json_response import PrettyJSONResponse
from linkedin_profile_api.linkedin.exceptions import AppError, InvalidProfileUrlError
from linkedin_profile_api.schemas.response import ErrorBody, ErrorResponse


def _request_id(request: Request) -> UUID:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, UUID):
        return existing
    return uuid4()


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> PrettyJSONResponse:
        payload = ErrorResponse(
            error=ErrorBody(code=exc.code, message=exc.message, request_id=_request_id(request))
        )
        return PrettyJSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> PrettyJSONResponse:
        mapped = InvalidProfileUrlError("Request validation failed.")
        payload = ErrorResponse(
            error=ErrorBody(code=mapped.code, message=mapped.message, request_id=_request_id(request))
        )
        return PrettyJSONResponse(status_code=mapped.status_code, content=payload.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception) -> PrettyJSONResponse:
        payload = ErrorResponse(
            error=ErrorBody(
                code="internal_error",
                message="An unexpected error occurred.",
                request_id=_request_id(request),
            )
        )
        return PrettyJSONResponse(status_code=500, content=payload.model_dump(mode="json"))
