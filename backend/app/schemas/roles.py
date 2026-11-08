"""Role and permission-catalogue schemas (Parth — US-49, FR-78)."""

from pydantic import BaseModel, Field, field_validator


class PermissionRead(BaseModel):
    name: str
    description: str
    group: str  # Workspace · Requirements · Review · Governance (the role editor's sections)


class _RoleFields(BaseModel):
    description: str | None = Field(default=None, max_length=500)

    @field_validator("permissions", check_fields=False)
    @classmethod
    def _unique(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else sorted(set(value))

    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class RoleCreate(_RoleFields):
    name: str = Field(min_length=1, max_length=80)
    permissions: list[str] = Field(min_length=1, max_length=64)


class RoleUpdate(_RoleFields):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    permissions: list[str] | None = Field(default=None, min_length=1, max_length=64)
