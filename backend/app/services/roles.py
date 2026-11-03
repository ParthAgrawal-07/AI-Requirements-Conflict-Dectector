"""Role queries (Parth — US-27, FR-48, ADR-20).

The roles a workspace can assign: the nine platform defaults plus the workspace's own custom roles
(US-49, Sprint 2 adds create/edit/delete here). Used by the Members screens and by the join-code
form, which may only offer roles a code is allowed to grant (FR-44, SX-14).

Authorisation never reads role names; this module only lists roles and says what they hold.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import role_allowed_via_code
from app.models import Role


def list_roles(db: Session, workspace_id: uuid.UUID) -> list[Role]:
    """Default roles first, then the workspace's custom roles, each group by name."""
    return list(
        db.scalars(
            select(Role)
            .where(Role.workspace_id.is_(None) | (Role.workspace_id == workspace_id))
            .options(selectinload(Role.permissions))
            .order_by(Role.is_default.desc(), Role.name)
        )
    )


def grantable_by_join_code(role: Role) -> bool:
    """May a join code hand out this role? Decided on permissions, so custom roles count too."""
    return role_allowed_via_code(role.permission_names)
