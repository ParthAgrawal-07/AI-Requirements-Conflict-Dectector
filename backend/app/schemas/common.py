"""Shared response schemas, mainly for accurate OpenAPI docs of error bodies."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Body of every non-2xx response (see docs/engineering/api-reference.md)."""

    error: ErrorBody


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope for every paginated list endpoint."""

    items: list[T]
    total: int = Field(description="Total matching rows, ignoring limit/offset")
    limit: int
    offset: int
