# User Roles & Permissions

**Stakeholder Roles, Team Roles, and Access Tiers**

| | |
|---|---|
| **Status** | Implemented in Sprint 0: JWT login, the `Role` enum and `require_roles(...)`. Workspace-scoping helper planned (T15, Sprint 2) |
| **Traces to** | FR-37, FR-38, FR-21, NFR-11, NFR-13 |

---

## 1. Application-Level Roles (Planned RBAC)

Derived from FR-37 (authenticated access), FR-38 (workspace-scoped access), FR-21/NFR-13 (protected requirements), and NFR-11 (role-based access control). These are the in-product roles the auth system (US-19) will need to support — distinct from the 10 requirements-elicitation stakeholders and the team roles below.

| Role (`Role` enum value) | Can do | Cannot do |
|---|---|---|
| Analyst (`analyst`, default) | Upload documents, view extractions, review/confirm/dismiss/merge flags, generate clarifications, view dashboard | Change similarity/ambiguity thresholds, mark requirements "protected" |
| Architect / Admin (`admin`) | Everything an Analyst can, plus tune thresholds (US-06), define ambiguity/dependency criteria (FR-16/17), manage workspace users | Bypass the protected-requirement review requirement (DR-05) |
| Compliance Reviewer (`compliance_reviewer`) | View/resolve findings on requirements marked "protected"; view full audit trail | Auto-resolve or bulk-dismiss protected-requirement findings |
| Executive / Read-Only (`read_only`) | View dashboard and executive summary reports (US-13, US-17) | Upload documents, act on findings, change configuration |
| System / Service Account (`service`) | Used by the async worker (Celery) and, in the deferred REST API (US-20), by third-party integrations | Access the UI directly |

*Auth mechanism for the MVP is JWT only (US-19); SSO/LDAP federation is named in FR-37 as an "or organization's existing SSO/LDAP where applicable" but is explicitly out of scope for the semester deliverable (see `overview.md`).*

## 2. Protected-Requirement Access Rule

This is a domain rule (DR-05), not just an access-control feature: requirements marked compliance-critical or regulatory are exempt from automatic duplicate-removal/merge suggestions and are routed to mandatory manual review regardless of which role is acting on them. NFR-13 requires that all access to protected requirements be logged for audit.

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

## 4. Project Team (10 members)

This is a third set of roles, separate from the two above: how the team divides the work. The original plan had 7 roles. The sprint plan ([`../sprint-plan.md`](../sprint-plan.md)) staffs them with 10 people in three groups: the 5 backend roles keep one owner each, the 2 frontend roles are split across 3 people by screen, and testing is its own 2-person group. The same table drives `.github/CODEOWNERS`.

| Group | Original role | Person (GitHub) | Owns |
|---|---|---|---|
| Backend | 1 — Document Ingestion | Bansil (@Bansil08) | `backend/app/ingestion/` — parsing, segmentation |
| Backend | 2 — Embedding & Similarity | Heet (@the-heet-shah) | `backend/app/embeddings/` — pgvector, candidate pairs, thresholds |
| Backend | 3 — LLM Classification | Keval (@kevaldarji6126) | `backend/app/classification/` — prompts, structured output |
| Backend | 4 — Clarification & Impact | Madhav (@PrimeNotFound) | `backend/app/clarification/` — questions, impact analysis |
| Backend | 5 — API & Orchestration | Parth (@ParthAgrawal-07) | `core/`, `api/`, `models/`, Alembic, Docker Compose |
| Frontend | 6 — Core UI | Pranshu (@pranshu-chovatiya) | Upload, requirements list, version history, dashboard UI |
| Frontend | 6 — Core UI | Abhijeet (@aprk05) | Findings, review, clarification, severity/threshold UI |
| Frontend | 7 — Visualization & DevOps | Dhvani (@DC-01051) | Graph (React Flow), impact UI, CI/CD, deployment |
| Testing | — | Abhyudit (@abhyudits) | Backend tests, classification accuracy benchmark |
| Testing | — | Affan (@Affan689) | Frontend tests, E2E, manual QA against acceptance criteria |
