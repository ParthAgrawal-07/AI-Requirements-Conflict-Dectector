"""Permission schemas (Parth — US-27). ``GET /me/permissions`` drives which actions the UI shows."""

import uuid

from pydantic import BaseModel

from app.schemas.auth import RoleRef


class MyPermissions(BaseModel):
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    # The effective role: the project-level override when the request names a project (FR-79).
    role: RoleRef
    permissions: list[str]
    # Held for protected requirements only (e.g. Compliance Reviewer's ``finding.review``).
    protected_only: list[str]
