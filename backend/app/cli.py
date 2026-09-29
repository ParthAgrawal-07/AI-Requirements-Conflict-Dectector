"""Admin command line (Role 5).

Run inside the backend container (or a local venv)::

    python -m app.cli create-user --email ana@example.com --name "Ana Shah" --role admin
    python -m app.cli seed-demo          # dev only: one user per role in "Demo Workspace"

There is deliberately no public sign-up endpoint: accounts are provisioned by an
administrator (IT/DevOps stakeholder requirement), so the first admin comes from here.
"""

import argparse
import getpass
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.database import session_scope
from app.core.errors import ConflictError
from app.core.security import WeakPasswordError
from app.models import Role
from app.services.users import create_user, get_or_create_workspace

DEMO_WORKSPACE = "Demo Workspace"
DEMO_PASSWORD = "demo-password-123"  # noqa: S105 — dev-only seed data, refused in production


def _cmd_create_user(args: argparse.Namespace) -> int:
    password: str = args.password or getpass.getpass("Password: ")
    with session_scope() as db:
        workspace = get_or_create_workspace(db, args.workspace)
        user = create_user(
            db,
            email=args.email,
            password=password,
            full_name=args.name,
            role=Role(args.role),
            workspace=workspace,
        )
        print(f"Created {user.role.value} {user.email} in workspace '{workspace.name}'")
    return 0


def _cmd_seed_demo(_: argparse.Namespace) -> int:
    if get_settings().is_production:
        print("Refusing to seed demo accounts with a known password in production", file=sys.stderr)
        return 1
    with session_scope() as db:
        workspace = get_or_create_workspace(db, DEMO_WORKSPACE)
        for role in Role:
            email = f"{role.value.replace('_', '.')}@demo.local"
            try:
                create_user(
                    db,
                    email=email,
                    password=DEMO_PASSWORD,
                    full_name=f"Demo {role.value.replace('_', ' ').title()}",
                    role=role,
                    workspace=workspace,
                )
                print(f"Created {email}")
            except ConflictError:
                print(f"Exists  {email}")
    print(f"\nDemo password for every account: {DEMO_PASSWORD}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="Create a user (and their workspace if new)")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True, help="Full name")
    create.add_argument("--role", choices=[r.value for r in Role], default=Role.ANALYST.value)
    create.add_argument("--workspace", default="Default Workspace")
    create.add_argument("--password", help="Omit to be prompted (keeps it out of shell history)")
    create.set_defaults(handler=_cmd_create_user)

    seed = sub.add_parser("seed-demo", help="Create one demo user per role (non-production only)")
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
