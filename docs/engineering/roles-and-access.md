# User Roles & Permissions

**Workspaces, Roles, Permissions and Access Tiers**

| | |
|---|---|
| **Status** | Implemented in Sprint 0–1 (rev. 5 plan): permission catalogue, nine default roles, memberships, `require_permission` |
| **Traces to** | FR-37, FR-38, FR-43–FR-48, FR-79, SX-06, ADR-12, ADR-14, ADR-20, NFR-11, NFR-27 |
| **Code** | `backend/app/core/permissions.py` (catalogue), `app/core/auth.py` (dependencies), `app/services/access.py` (resolution) |
| **Contract** | [`../contracts/permissions.md`](../contracts/permissions.md) |

---

## 1. How access works

**People belong to workspaces through memberships; what they may do is decided by permissions.**

```
User ──< Membership >── Workspace ──< Project ──< Document ──< Requirement
              │
              └── Role ──< RolePermission   (a permission *name* from the catalogue)
```

* A **user** has no role of their own. They have one *active membership* (`ended_at IS NULL`) in each
  workspace they belong to, each with its own role (FR-46). The only account-level role is
  `users.platform_role`: `platform_admin` (created by the CLI, may create workspaces — FR-37, FR-43) or
  `service` (reserved for API keys, post-MVP).
* A **role** is a named set of permissions. The nine **default roles** are platform-wide and immutable;
  custom roles (US-49, Sprint 2) belong to one workspace.
* Code checks **permission names, never role names** (ADR-20). Adding a role or changing what a role may do
  never touches route code.

### Every request, in this order

1. **Authenticate** — a valid bearer token for an *active* user, else **401**.
2. **Find the tenant** — the path names a workspace, project, document… and it resolves to a workspace
   (and project). Unknown id → **404**; a malformed id → **422**.
3. **Membership** — the user needs an *active* membership in that workspace, read from the database on
   **every** request, so removing a member or changing a role applies on their next request. No membership
   → **404, never 403** (ADR-12, NFR-27): a stranger cannot tell "forbidden" from "does not exist".
4. **Role** — the workspace role, or the **project-level override** (`project_members.role_override_id`,
   FR-79) when the request is about a project.
5. **Permission** — the role must hold the route's permission, else **403**.

Access to a project requires membership of its *workspace* (FR-38). `project_members` lists who is on a
project's team and may carry a role override; it is not an extra gate in the MVP.

**A project role override replaces the workspace role inside that project** (FR-79) — it can raise or lower someone's
permissions *there*: a workspace Viewer given a Project Manager override gets `baseline.manage` in that project only.
That is intended. The limits: never above the permissions of the person setting it, never `workspace.manage`, and only
for an active workspace member (`contracts/permissions.md` §2a).

### What a route must declare

Exactly one of these appears on every `/api/v1` route (a test fails otherwise — a forgotten permission cannot ship):

| Declaration | Meaning |
|---|---|
| `require_permission("x")` | the caller holds `x` in the workspace/project the path names |
| `require_any_permission("x", "y")` | at least one; the handler then checks the specific one it needs |
| `authenticated_only` | any signed-in user, no workspace involved (`/auth/me`, `/me/permissions`, `GET/POST /workspaces`) |
| `public_route` | no login (`/auth/login`, `/auth/signup`) — a two-entry allow-list in the tests |

## 2. Permission catalogue and default roles

Source of truth: `app/core/permissions.py` (mirrors spec §1.22). `✓*` = held for protected requirements only.

| Permission | What it allows | Own | Adm | PM | BA | Dev | QA | Stk | Comp | View |
|---|---|---|---|---|---|---|---|---|---|---|
| `workspace.manage` | Workspace settings, transfer ownership, delete | ✓ |  |  |  |  |  |  |  |  |
| `roles.manage` | Create and edit custom roles | ✓ | ✓ |  |  |  |  |  |  |  |
| `members.manage` | Change roles, remove members, approve join requests (PM: own projects) | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `joincode.manage` | Create and revoke join codes (PM: own projects) | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `project.manage` | Create projects, edit settings, budget, approvals | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `project.context` | Write or edit the project brief and context; confirm AI-drafted fields | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `srs.generate` | Generate an updated SRS draft; edit and accept its sections | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `srs.publish` | Publish an SRS version; override the readiness checklist with a reason | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `channel.manage` | Create, rename, archive channels | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `message.post` | Post, reply, mention | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `req.propose` | Propose requirements, drafts, lint, pre-flight | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `req.comment` | Comment on requirements | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `req.vote` | Support or oppose | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `req.link` | Assert links between requirements | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `doc.upload` | Upload SRS as proposals | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `baseline.manage` | Upload SRS as baseline, freeze snapshots, approve Proposed requirements | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `issue.open` | Open issues, comment on issues | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `issue.manage` | Assign, label, close any issue | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `rcr.open` | Open change requests | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| `rcr.review` | Review when requested (approval counts if eligible under FR-65) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `rcr.merge` | Merge an approved change request | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `finding.review` | Confirm, dismiss, merge, reclassify findings | ✓ | ✓ | ✓ | ✓ |  |  |  | ✓* |  |
| `req.protect` | Mark requirements protected | ✓ | ✓ |  |  |  |  |  | ✓ |  |
| `protected.signoff` | Sign off findings and changes on protected requirements |  |  |  |  |  |  |  | ✓ |  |
| `req.implement` | Mark Approved → Implemented | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `audit.export` | Export the audit trail | ✓ | ✓ |  |  |  |  |  | ✓ |  |
| `view` | See dashboards, map, analytics, timelines; export reports | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Notes:

* **Join codes can never grant a privileged role** (FR-44, NFR-35): Owner, Admin, or any role (custom ones too)
  holding `workspace.manage` or `roles.manage`. Enforced in `membership.add_member` / `add_project_member`
  (`via_join_code=True`), decided on permissions, not names.
* A workspace always has at least one active Owner (enforced when members are changed — US-26, Sprint 2).
* `finding.review` for the Compliance Reviewer is **protected only**: the permission is held but may be exercised
  only on protected requirements. This **fails closed**: `require_permission("finding.review")` refuses such a holder
  unless the route opts in with `allow_protected_only=True` and then checks the requirement
  (`ctx.can(..., protected_requirement=requirement.is_protected)`); `ctx.can(...)` is safe by default too.
  `GET /me/permissions` reports these permissions in `protected_only`. Nothing compares role names.
* The Owner holds every permission **except** `protected.signoff` (separation of duties: only the Compliance Reviewer
  signs off protected requirements).
* *Project Manager* holds `members.manage` and `joincode.manage` "for own projects" in the spec; the
  own-project scoping arrives with the members and join-code endpoints (Sprint 1–2, Madhav / Parth).

### Role names are display data

The names are stored in `roles.name` so they can be shown and chosen in the UI. Never write
`if role.name == "Owner"` — check the permission the action needs.

## 2a. Protected-Requirement Access Rule

This is a domain rule (DR-05), not just an access-control feature: requirements marked compliance-critical or
regulatory are exempt from automatic duplicate-removal/merge suggestions and are routed to mandatory manual
review regardless of which role is acting on them. NFR-13 requires that all access to protected requirements
be logged for audit. (Implementation: US-18, Sprint 6 — `protected.signoff`.)

## 2b. Sign-up and workspace creation

* **No open sign-up** (SX-02): `POST /auth/signup` needs a valid join code and creates the account and its
  membership in one transaction. A bad code leaves nothing behind. Attempts are limited per IP and per e-mail.
* **First account:** `python -m app.cli create-admin` creates the platform administrator (FR-37).
* **Workspaces:** created by platform administrators — or by any signed-in user if
  `ALLOW_USER_WORKSPACE_CREATION=true` (FR-43). The creator becomes the Owner. Workspace **names are not unique**
  (display labels; a uniqueness error would tell one tenant that another tenant's workspace exists).
* **Sign-up cannot enumerate accounts:** an invalid code and an already-registered e-mail get the identical
  `400 signup_refused`, and the password policy is checked before the e-mail is looked at.
* **Projects** start in `setup`; analysis is disabled until the context is confirmed (FR-103).

## 3. Requirements-Elicitation Stakeholders (10 groups)

These are the people the requirements were elicited from — the intended users and beneficiaries of the finished system, not team members. Each maps to specific FR/NFR items in `requirements-spec.md`.

| Stakeholder | Primary interest | Maps to app role |
|---|---|---|
| Business Analysts / Requirements Engineers | Primary end users — upload, review, resolve findings | Analyst |
| Project Managers | Impact analysis, report delivery, escalation tracking | Analyst / Executive (reporting) |
| Software Architects / Senior Developers | Threshold tuning, ambiguity/dependency definitions | Architect / Admin |
| Client / Product Owner | Success-metric configuration, scope control | Architect / Admin |
| QA / Test Engineers | Clarification quality, low-fidelity preview validation | Analyst |
| Executive Sponsor / Budget Holder | ROI summary, rollout approval | Executive / Read-Only |
| Legal / Compliance Team | Protected requirements, audit trail | Compliance Reviewer |
| IT / DevOps / System Administrators | Auth, workspace access, deployment | Architect / Admin |
| End Customers (indirect) | Never interact with the tool directly — outcome-tracked only | None |
| Third-Party API Consumers | Deferred (US-20) — REST API access | System / Service Account (future) |

## 4. Project Team Roles (10 members)

Distinct from the two role sets above — this is how the 10-person team divides implementation ownership ([`IT314_RCD_Sprint_Plan_v5.md` §2](../planning/v5/IT314_RCD_Sprint_Plan_v5.md#2-team-and-areas-of-ownership)). See `architecture.md` for how these map to repo modules.

| Member | Primary area |
|---|---|
| Parth | Backend lead: auth, memberships, permissions and roles, review state, lifecycle, approvals and merge, versions, baselines, audit |
| Dhavni didi | DevOps and real-time: Docker, CI/CD, Celery, WebSocket gateway, event bus, graph API and deltas, issues backend, deployment |
| Bansil | Ingestion and authoring: extraction, project context, requirement posts and drafts, ownership, change-request intake, votes, watches and links, updated SRS generator and export |
| Pranshu | Frontend lead: shell, login, channels, composer, requirements table, issues UI, dashboard, baselines, map preview and time slider, analytics |
| Heet | Embeddings and retrieval: vector store, candidates, incremental retrieval, similar-requirement hints, relationship queries, search |
| Keval | Classification and LLM: clients, prompts, context pack, classifier, severity, budget, lint catalogue, pre-flight and AI wording, SRS section prompts |
| Madhav | Clarification and consequences: questions, impact engine, consequence checks, risk, notifications, join codes backend, AI resolution suggestions |
| Abhijeet | Frontend: members, roles and join codes UI, project setup wizard, findings and review, live map UI, change editor and change-request page, inbox, compliance UI |
| Abhyudit | QA — accuracy and backend: benchmark, evaluation harness, API and database tests |
| Affan | QA — E2E, performance, security: Playwright, permission tests, join-code abuse tests, WebSocket and load tests, accessibility |
