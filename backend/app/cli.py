"""Admin command line (Role 5; Parth — FR-37, SX-02).

Run inside the backend container (or a local venv)::

    python -m app.cli create-admin --email ana@example.com --name "Ana Shah"
    python -m app.cli seed-demo     # dev only: "Demo Workspace" with one member per default role

There is deliberately no open sign-up (SX-02): people join with a code (``POST /auth/signup``).
The CLI exists for exactly one job in production — creating the **first platform administrator**
(FR-37), who then creates a workspace, becomes its Owner and issues join codes. ``seed-demo`` is
for development only and refuses to run unless ENVIRONMENT is ``development`` or ``test``
(staging and production are refused: the accounts have a published password).
"""

import argparse
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Environment, get_settings
from app.core.database import session_scope
from app.core.errors import ConflictError
from app.core.permissions import DefaultRole
from app.core.security import WeakPasswordError
from app.models import PlatformRole, Project, ProjectStatus, Workspace
from app.services.membership import active_membership, add_member, get_default_role
from app.services.projects import create_project
from app.services.users import create_user, get_user_by_email
from app.services.workspaces import create_workspace

DEMO_WORKSPACE = "Demo Workspace"
DEMO_PROJECT = "Demo Project"
DEMO_PASSWORD = "demo-password-123"  # noqa: S105 — dev-only seed data, refused outside development/test


def _cmd_create_admin(args: argparse.Namespace) -> int:
    with session_scope() as db:
        existing = get_user_by_email(db, args.email)
        if existing is not None:
            if not args.promote:
                raise ConflictError(
                    f"{existing.email} already exists; pass --promote to make them a platform admin"
                )
            existing.platform_role = PlatformRole.PLATFORM_ADMIN
            print(f"Promoted {existing.email} to platform administrator")
            return 0
        password: str = args.password or getpass.getpass("Password: ")
        user = create_user(
            db,
            email=args.email,
            password=password,
            full_name=args.name,
            platform_role=PlatformRole.PLATFORM_ADMIN,
        )
        print(f"Created platform administrator {user.email}")
    return 0


def _demo_email(role: DefaultRole) -> str:
    return f"{role.value.lower().replace(' ', '.')}@demo.local"


def _seed_demo(db: Session) -> None:
    """Idempotent: re-running adds whatever is missing and leaves the rest alone."""
    workspace = db.scalar(
        select(Workspace).where(Workspace.name == DEMO_WORKSPACE).order_by(Workspace.created_at)
    )

    for role in DefaultRole:
        email = _demo_email(role)
        user = get_user_by_email(db, email)
        created = user is None
        if user is None:
            user = create_user(
                db,
                email=email,
                password=DEMO_PASSWORD,
                full_name=f"Demo {role.value}",
                commit=False,
            )
        if workspace is None:
            # The first role in the enum is Owner; it creates the workspace and owns it.
            workspace = create_workspace(db, owner=user, name=DEMO_WORKSPACE)
        elif active_membership(db, user.id, workspace.id) is None:
            add_member(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                role_id=get_default_role(db, role).id,
                actor_id=user.id,
                commit=False,
            )
        print(f"{'Created' if created else 'Exists '} {email}  ({role.value})")

    if workspace is None:  # DefaultRole is never empty, so the loop above always set it
        raise RuntimeError("demo workspace was not created")
    project = db.scalar(
        select(Project).where(Project.workspace_id == workspace.id, Project.name == DEMO_PROJECT)
    )
    if project is None:
        owner = get_user_by_email(db, _demo_email(DefaultRole.OWNER))
        if owner is None:
            raise RuntimeError("demo owner was not created")
        project = create_project(db, workspace_id=workspace.id, creator=owner, name=DEMO_PROJECT)
        # Development convenience only: real projects stay in Setup until their context is
        # confirmed (US-60). The demo project is active so analysis can be exercised right away.
        project.status = ProjectStatus.ACTIVE
        print(f"Created project '{DEMO_PROJECT}' (active)")
    db.commit()


def _cmd_seed_demo(_: argparse.Namespace) -> int:
    environment = get_settings().environment
    if environment not in (Environment.DEVELOPMENT, Environment.TEST):
        print(
            f"Refusing to seed demo accounts with a known password in a '{environment}' "
            "environment: seed-demo is for development only",
            file=sys.stderr,
        )
        return 1
    with session_scope() as db:
        _seed_demo(db)
    print(f"\nDemo password for every account: {DEMO_PASSWORD}")
    print("Development join code (until join codes land): TEST1234")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("create-admin", help="Create the platform administrator (FR-37)")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True, help="Full name")
    admin.add_argument("--password", help="Omit to be prompted (keeps it out of shell history)")
    admin.add_argument(
        "--promote",
        action="store_true",
        help="If the e-mail already has an account, make that account a platform administrator",
    )
    admin.set_defaults(handler=_cmd_create_admin)

    seed = sub.add_parser(
        "seed-demo",
        help="Create a demo workspace, one member per default role (development/test only)",
    )
    seed.set_defaults(handler=_cmd_seed_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.handler(args)
    except (WeakPasswordError, ConflictError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
