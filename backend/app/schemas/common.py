"""Shared response schemas, mainly for accurate OpenAPI docs of error bodies."""

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Body of every non-2xx response (see docs/engineering/api-reference.md)."""

    error: ErrorBody
