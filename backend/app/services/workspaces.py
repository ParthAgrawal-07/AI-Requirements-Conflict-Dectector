"""Workspace service (Parth — US-24, FR-43, FR-46).

Creating a workspace makes the creator its **Owner** in the same transaction, so a workspace
never exists without an owner. Names are display labels and are **not unique**: a uniqueness
error would tell one tenant that another tenant's workspace exists. Who *may* create one is decided by the route (platform admins, or
any user when ``ALLOW_USER_WORKSPACE_CREATION`` is on — FR-43); this module only does the work.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import AuditAction, AuditLog, User, Workspace
from app.services.membership import add_member, get_default_role


def create_workspace(db: Session, *, owner: User, name: str) -> Workspace:
    """Create a workspace owned by ``owner``, in one transaction."""
    workspace = Workspace(name=name.strip())
    db.add(workspace)
    db.flush()

    add_member(
        db,
        workspace_id=workspace.id,
        user_id=owner.id,
        role_id=get_default_role(db, DefaultRole.OWNER).id,
        actor_id=owner.id,
        commit=False,
    )
    db.add(
        AuditLog(
            workspace_id=workspace.id,
            actor_id=owner.id,
            action=AuditAction.WORKSPACE_CREATED,
            details={"workspace_id": str(workspace.id)},
        )
    )
    db.commit()
    return workspace


def get_workspace(db: Session, workspace_id: uuid.UUID) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def rename_workspace(db: Session, *, workspace: Workspace, actor: User, name: str) -> Workspace:
    name = name.strip()
    if name == workspace.name:
        return workspace
    workspace.name = name
    db.add(
        AuditLog(
            workspace_id=workspace.id,
            actor_id=actor.id,
            action=AuditAction.WORKSPACE_UPDATED,
            details={"changed": ["name"]},
        )
    )
    db.commit()
    return workspace
