# Contract — permissions, access and the Sprint 0–1 hand-offs (Parth)

| | |
|---|---|
| **Producer** | Parth (backend lead) |
| **Consumers** | everyone who writes a route · Pranshu / Abhijeet (UI) · Madhav (join codes) · Bansil (context, extraction) · Affan (permission tests) |
| **Status** | Implemented. Replaces the "constant list" stub of the hand-off table (S0 end) |
| **Code** | `backend/app/core/permissions.py`, `app/core/auth.py`, `app/services/access.py`, `app/services/membership.py`, `app/services/projects.py`, `app/services/signup.py` |

## 1. Protecting a route (everyone)

Every `/api/v1` route declares **exactly one** of these, in its signature. A test (`test_access_invariants.py`)
fails the build if one is missing, so a forgotten permission cannot ship.

```python
from typing import Annotated
from app.api.deps import DbSession, requires, requires_any
from app.services.access import AccessContext

@router.post("/projects/{project_id}/channels")
def create_channel(
    project_id: uuid.UUID,
    body: ChannelCreate,
    ctx: Annotated[AccessContext, requires("channel.manage")],   # ← the permission, from the catalogue
    db: DbSession,
) -> ChannelRead:
    ...  # ctx.user, ctx.workspace_id, ctx.project_id, ctx.can("x"), ctx.permissions
```

| Need | Use |
|---|---|
| one permission | `requires("x")` |
| one of several (the handler then checks which) | `requires_any("x", "y")` + `ctx.can("x")` |
| any signed-in user, no workspace in the path | `Authenticated` (`authenticated_only`) — **adding to this list needs a conscious edit of the allow-list in the test** |
| no login | `PublicRoute` — only `/auth/login` and `/auth/signup` |

**Protected-only permissions fail closed.** The Compliance Reviewer holds `finding.review` *for
protected requirements only* (spec §1.22). `require_permission("finding.review")` therefore **refuses** that
holder by default; a route that really handles protected requirements opts in with
`requires("finding.review", allow_protected_only=True)` and must then check the requirement it acts on:

```python
if not ctx.can("finding.review", protected_requirement=requirement.is_protected):
    raise ForbiddenError()
```

`ctx.can(permission)` is safe by default too — it answers `False` for a protected-only grant unless you say the
requirement is protected. Opted-in routes are listed in `PROTECTED_ONLY_OPT_INS` in `test_access_invariants.py`;
adding one is a conscious decision. (US-10, Sprint 3, will be the first.)

**Rules**

* Use permission **names** from `app/core/permissions.py`. **Never compare role names.** A typo in a permission
  name raises `ValueError` when the app starts.
* The path must contain a parameter the access layer can resolve to a tenant: `workspace_id`, `project_id`,
  `document_id`, `requirement_id` today. **Use exactly these parameter names.**
* Not a member → **404** (never 403); member without the permission → **403**. Membership and role are re-read on
  every request.
* Need a new kind of resource in a path (`channel_id`, `issue_id`, `change_request_id`, `finding_id`…)? Register a
  resolver next to your model, once, at import time:

```python
from app.services.access import Scope, register_scope_resolver

def _channel_scope(db: Session, channel_id: uuid.UUID) -> Scope | None:
    row = db.execute(select(Project.workspace_id, Channel.project_id)
                     .join(Project, Project.id == Channel.project_id)
                     .where(Channel.id == channel_id)).first()
    return None if row is None else Scope(row[0], row[1])

register_scope_resolver("channel_id", _channel_scope)    # returns None if the channel does not exist
```

* Add a permission? Add it to `PERMISSIONS` **and** `_GRANTS` in `permissions.py`, and write a **new** migration that
  inserts the `role_permissions` rows. `tests/db/test_default_roles.py` fails if the two drift apart.

### Test helpers (in `tests/conftest.py`)

`make_user(role=DefaultRole.DEVELOPER)` · `user` (a Business Analyst) · `project` (active) ·
`make_project(status=ProjectStatus.SETUP)` · `make_workspace()` (another tenant) · `make_requirement()`.
For each new endpoint write three API tests (success, 403 missing permission, 404 other workspace).

## 2. `GET /me/permissions` (Pranshu, Abhijeet)

`GET /api/v1/me/permissions?project=<id>` (or `?workspace=<id>`) →
`{ workspace_id, project_id, role: {id, name, is_default}, permissions: [..], protected_only: [..] }`.
Use it to **show or hide** actions (`usePermissions()`); it is a convenience, never the gate — the server enforces every
permission regardless. `protected_only` lists permissions held for protected requirements only (the Compliance Reviewer's
`finding.review`). `404` = not a member. `GET /auth/me` returns the user's memberships for the workspace switcher.

## 2a. Project-level roles (FR-79)

A project team entry (`project_members`) may carry a **role override** that *replaces* the member's workspace role
**inside that project only** — it can raise or lower their permissions there (a workspace Viewer given a Project
Manager override gets `baseline.manage` in that project, and nowhere else). That is intended by FR-79. The limits:

* the override must be a default role or a custom role of the **same workspace**, and can never carry
  `workspace.manage` (ownership is not per-project) — enforced by `membership.add_project_member`;
* the person must already be an **active member of the workspace** — a team is a subset, never a way in;
* **never above the PM's own permissions** (FR-79): whoever *sets* an override may only give permissions they hold
  themselves. This is enforced by `PUT /projects/{p}/members/{u}` (Sprint 2); until that endpoint exists nothing
  exposes the setter, and `add_project_member` is called only by the join-code service (below).

## 3. Join codes (Madhav ⇄ Parth)

**Madhav provides** `app/services/join_codes.py` with:

```python
def redeem(db: Session, code: str, user: User) -> Membership | JoinRequest: ...
```

* Called by `POST /auth/signup` right after the new user row is **flushed (not committed)**. It may commit or only
  flush; the user is in the same session.
* On success: create the membership through **`membership.add_member(db, workspace_id=…, user_id=user.id, role_id=…,
  via_join_code=True, commit=False)`** (it enforces "one active membership", the role's workspace and writes the audit row), and for a
  project-scoped code also `membership.add_project_member(db, project=…, user=user, via_join_code=True,
  commit=False)`. **`via_join_code=True` is mandatory**: it is what stops a code from ever granting a privileged
  role — Owner, Admin, or *any* role holding `workspace.manage` or `roles.manage` (checked on permissions, so custom
  roles count). Both functions also validate the role (default or this workspace's) and the user's workspace
  membership, and write an audit row. Return the `Membership`. If the code needs approval, create the join request and return it (anything that is not a `Membership`
  means "pending approval").
* On **any** failure raise **`app.core.errors.InvalidJoinCodeError`** — one error, one message, for invalid, expired,
  used-up and revoked codes (NFR-35). Parth's sign-up code rolls the new account back and answers with the same
  `400 signup_refused` it gives for an already-registered e-mail, so **sign-up cannot be used to find out which
  e-mails have accounts**. (Any other 4xx `AppError` from `redeem` is folded into the same answer; 429/503 pass through.)
  Your own `POST /join` may use `InvalidJoinCodeError` directly.
* The per-address/per-email limit on `POST /auth/signup` is already enforced by Parth's route using
  `app/core/rate_limit.py` (Redis, fixed window; if Redis is unreachable it degrades to a per-process counter and logs
  a warning rather than blocking every sign-up). The "address" is `client_ip(request)`: behind a reverse proxy set
  `TRUSTED_PROXY_HOPS` (Render: 1), otherwise everyone shares one limit. Reuse `enforce(limiter, key, limit=…)` for `POST /join`
  rather than writing a second limiter.

**Until it merges**, `get_join_code_redeemer()` uses a development stub: the code `TEST1234` joins "Demo Workspace"
(created by `make seed-demo`) as Developer; it is refused outside development/test. When `app/services/join_codes.py`
exists with a `redeem`, it is picked up automatically — no change in Parth's code.

## 4. The ContextGate — no analysis while a project is in Setup (Bansil, Dhavni, Keval, Heet, Madhav)

A project starts in `setup` (`projects.status`). Anything that **starts analysis** must call, first:

```python
from app.services.projects import ensure_project_active
ensure_project_active(project)                       # raises ProjectInSetupError → 409 project_in_setup
ensure_project_active(project, missing_fields=[...]) # Bansil: name what is still unconfirmed (FR-103)
```

Call it in: the analysis orchestrator (S2), the composer / requirement posts (S3), change requests and consequence
checks (S4). Uploading a document and extracting its requirements is **not** analysis and is allowed in Setup.
**Nothing moves a project from `setup` to `active` yet** — that transition belongs to the context work. **Bansil**
(US-60) activates a project by setting `project.status = ProjectStatus.ACTIVE` and `project.context_version` when the
context is confirmed; `PATCH /projects/{p}` deliberately cannot do it. Until then every project created through the API
stays in Setup (only the `seed-demo` project is activated, in development).

## 5. Schema decisions the team must know (migrations)

Migration **0004** (Parth) is deliberately a little larger than the design-update table, because Sprint 1 stories need
these columns before the migrations that were to carry them:

| Column | Design update said | Now |
|---|---|---|
| `projects.status`, `projects.context_version` | `0011_project_context` | created in **0004** (US-24 creates projects in Setup) — **Bansil: 0011 must not add them again** |
| `requirements.state`, `origin`, `owner_id` | `0006_lifecycle_runs` | created in **0004** (US-02 writes and US-04 lists them in Sprint 1) — **0006 keeps** `origin_message_id`, composer fields, `requirement_drafts`, `analysis_runs`… |
| `documents.import_mode`, `stakeholder_group` | (US-01) | created in **0004** |
| `role_permissions.protected_only` | — | created in **0004** (the Compliance Reviewer's protected-only `finding.review`) |
| `requirements.document_id` | — | still NOT NULL; 0006 (or whoever adds posts) will need to make it nullable for requirement posts, with a `CHECK` that `origin = 'document'` implies a document |

`0003` narrows `findings.severity` to low/medium/high (`critical` → `high`) and records the `escalated` audit action.
Existing data is backfilled by 0004 (one active project per workspace, one membership per user, first admin → Owner).
**`0004a`** (PR review) is a separate follow-up so it applies whether or not 0004 already ran somewhere: it drops the
platform-wide UNIQUE on `workspaces.name` and fixes the Owner role's description. Run the verification in
`docs/engineering/migration-runbook.md` against a copy of real data before merging.

Requirement writes: `app/services/processing.py` (extraction persist step) now sets `project_id`, `state`
(`Approved` for a baseline import, else `Proposed`), `origin='document'` and `stakeholder_group`. **Bansil:** keep these
when US-02 moves extraction into `app/ingestion/extract.py`.
