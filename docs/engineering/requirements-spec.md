# Requirements Specification

**Functional, Non-Functional & Domain Requirements**

| | |
|---|---|
| **Source** | IT314 Lab Assignment 6 — Requirement Formalization & Process Modeling |
| **Numbering** | FR-01–FR-41 · NFR-01–NFR-23 · DR-01–DR-12 |
| **Status** | All requirements below are planned — no implementation exists yet |

---

## 0. Important Note on Numbering

Two requirements artifacts exist in parallel and have **NOT** yet been reconciled into a single canonical numbering scheme:

- This document uses the official Lab 6 submission numbering (FR-01–FR-41 / NFR-01–NFR-23 / DR-01–DR-12), which is what the Consolidated Product Backlog (see `feature-catalog.md`) traces its FR references against in some places.
- A separately maintained "Consolidated Requirements Baseline" draft (~34 FR / ~24 NFR / ~14 DR, grouped by pipeline stage) was developed in parallel by the team and uses different numbers for the same concepts.
- The issue taxonomy itself is also inconsistent across the two artifacts: DR-01 below states the "four standard categories" (Conflicting, Duplicate, Ambiguous, Dependent), while the team's adopted, authoritative taxonomy is 5 categories, adding **Incomplete** — three of the seven original drafts used 4 categories, but one draft plus the official project brief text explicitly include "Incomplete," so 5 was adopted.

> **Open action item:** reconcile these into one canonical FR/NFR/DR numbering scheme before Sprint 1 development begins, and correct DR-01 to reflect the 5-category taxonomy. Tracked in `decision-log.md` and `project-status.md`.

## 1. Functional Requirements (FR)

### 1.1 Document Ingestion — FR-01–FR-06

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-01 | The system shall allow an authorized user to upload an SRS document in PDF or Word (DOCX) format. | Architects; IT/DevOps |
| FR-02 | The system shall validate that an uploaded document is a supported, uncorrupted file and reject/notify the user otherwise. | Architects |
| FR-03 | The system shall extract raw text from the uploaded document and segment it into individual, distinct requirement statements, preserving structure where present (numbered lists, REQ-IDs). | Business Analysts; Architects |
| FR-04 | The system shall preserve original requirement identifiers and wording from the source document rather than regenerating its own numbering scheme. | Business Analysts |
| FR-05 | The system shall associate extracted requirements with their source document and, where supplied, the originating stakeholder/group (provenance). | Business Analysts; Product Owner |
| FR-06 | The system shall allow a user to correct extraction or segmentation errors before analysis begins. | Business Analysts |

### 1.2 Embedding & Similarity Pre-Filter — FR-07–FR-10

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-07 | The system shall generate a vector embedding for each extracted requirement statement. | Architects / Senior Developers |
| FR-08 | The system shall store requirement embeddings in a vector-searchable data store (e.g., pgvector). | Architects / Senior Developers |
| FR-09 | The system shall compute pairwise similarity between requirements and generate a filtered candidate set of pairs above a configurable similarity threshold, so that not every pair requires LLM classification. | Architects; Business Analysts |
| FR-10 | The system shall allow the similarity threshold to be tuned via configuration, without requiring a code change. | Architects / Senior Developers |

### 1.3 AI Classification — FR-11–FR-17

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-11 | The system shall classify each candidate requirement pair into one of: Conflicting, Duplicate, Ambiguous, or Dependent. | Business Analysts; Architects |
| FR-12 | The system shall distinguish true duplicates from merely similar requirements using the configurable similarity threshold and LLM judgment together. | Business Analysts |
| FR-13 | The system shall return a confidence/trust score alongside each classification result so users can judge reliability before acting on it. | Business Analysts |
| FR-14 | The system shall attach supporting context to every flagged issue: related requirement ID(s), source document section, and a natural-language rationale for the flag. | QA Engineers; Business Analysts |
| FR-15 | The system shall validate and structure classification output (schema-valid) before it is persisted or displayed. | Architects / Senior Developers |
| FR-16 | The system shall allow authorized users to define and adjust the criteria that qualify a requirement as "ambiguous" (e.g., vague terms, missing acceptance criteria). | Architects / Senior Developers |
| FR-17 | The system shall allow authorized users to define and adjust the criteria that qualify two requirements as "dependent" on one another. | Architects / Senior Developers |

### 1.4 Human Review & Feedback — FR-18–FR-21

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-18 | The system shall allow authorized users to confirm, dismiss (as a false positive), merge, or reclassify a flagged issue. | Senior Developers; Business Analysts |
| FR-19 | The system shall persist all classification results — including dismissed ones — for audit and traceability. | Legal / Compliance Team |
| FR-20 | The system shall retain the original AI-generated finding when a human corrects or reclassifies it, rather than overwriting it. | Business Analysts; QA Engineers |
| FR-21 | The system shall allow compliance-critical requirements to be marked "protected," preventing them from being auto-flagged as duplicate/conflicting or removed without explicit manual sign-off. | Legal / Compliance Team |

### 1.5 Clarification Workflow — FR-22–FR-23

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-22 | For every requirement flagged as Ambiguous or Conflicting, the system shall generate a clarification question sufficient for a QA engineer to resolve the issue without further discussion. | QA Engineers |
| FR-23 | The system shall allow a user to mark a clarification question as answered and attach the resolution text. | QA Engineers; Business Analysts |

### 1.6 Change & Impact Analysis — FR-24–FR-26

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-24 | Whenever a requirement is modified, the system shall perform a change-impact analysis identifying all requirements, related design elements, or test cases affected. | Project Managers |
| FR-25 | The system shall present the list of potentially impacted requirements before a proposed change is saved. | Project Managers; Architects |
| FR-26 | The system shall maintain a version history for every requirement, including prior text, edits, and resolution status, to support change comparison and audit. | Architects; Legal / Compliance |

### 1.7 Dashboard, Visualization & Reporting — FR-27–FR-32

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-27 | The system shall display a summary dashboard showing counts of flagged issues by type (Conflict / Duplicate / Ambiguous / Dependent). | Project Managers; Business Analysts |
| FR-28 | The system shall allow drill-down navigation from a summary count to the underlying list of flagged requirements. | Business Analysts |
| FR-29 | The system shall render a visual relationship graph of requirements, with requirements as nodes and detected relationships as connections. | Architects; Project Managers |
| FR-30 | The system shall allow users to generate and export flagged-issue and impact-analysis reports in multiple formats (on-screen dashboard, PDF/CSV, scheduled email digest). | Project Managers |
| FR-31 | The system shall provide a low-fidelity preview mode of flagged output so stakeholders can validate usability before full deployment. | QA Engineers |
| FR-32 | The system shall generate an aggregated, executive-level summary report of risk/cost-reduction metrics suitable for periodic distribution to sponsors. | Executive Sponsor / Budget Holder |

### 1.8 Configuration & Scope Control — FR-33–FR-34

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-33 | The system shall allow the Client/Product Owner to configure the success metrics/KPIs to be tracked (e.g., reduction in late-stage change requests, faster sign-off time). | Client / Product Owner |
| FR-34 | The system shall support configuration of an explicit "out of scope" list of requirement types or SRS sections excluded from automated analysis. | Client / Product Owner |

### 1.9 Escalation & Audit Trail — FR-35–FR-36

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-35 | The system shall maintain a traceable escalation log recording who a flagged conflict was routed to and its resolution status/history. | Business Analysts |
| FR-36 | The system shall maintain a complete, exportable audit trail of all automated flags, manual overrides, and sign-offs for compliance and executive review. | Legal / Compliance Team; Executive Sponsor |

### 1.10 Authentication & External Integration — FR-37–FR-41

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-37 | The system shall require user authentication (JWT-based, or the organization's existing SSO/LDAP where applicable) before granting access to any document, project, or dashboard. | IT/DevOps / System Admins |
| FR-38 | The system shall associate uploaded documents and analysis results with the uploading user/workspace and restrict access accordingly. | IT / DevOps |
| FR-39 | The system shall provide read/write integration with common engineering tools (e.g., Jira, Confluence, GitHub) to import requirements and export flagged issues as tickets. | IT/DevOps / System Admins |
| FR-40 | The system shall expose a documented, versioned REST API (JSON) allowing third-party developers to submit SRS content and retrieve conflict/ambiguity analysis results programmatically, with configurable per-consumer rate limits. | Third-Party API Consumers |
| FR-41 | The system shall provide a mechanism to intake survey or existing customer-feedback data on how delayed/unclear requirements affected end customers. | End Customers (Indirect) |

*FR-39, FR-40, FR-41 are industry-extension items and are explicitly out of scope for the semester MVP (see `overview.md`, Section 3).*

## 2. Non-Functional Requirements (NFR)

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Complete conflict/ambiguity analysis of a standard-size SRS document within an agreed target time (e.g., under 5 minutes for a ~100-page / 150–300-requirement doc), via async job queue. |
| NFR-02 | Performance | The analysis API shall respond to synchronous requests within an agreed SLA (e.g., 95% under 2s for documents below a defined size). |
| NFR-03 | Performance | The dashboard shall load and render initial results within an agreed target time (e.g., 3s) on a standard broadband connection. |
| NFR-04 | Scalability | Support a target number of concurrent analysis jobs from multiple users/teams (e.g., ≥50) without material per-job degradation. |
| NFR-05 | Scalability | The embedding pre-filter shall reduce LLM classification calls by a significant margin (e.g., ≥70%) vs. brute-force all-pairs comparison, avoiding O(n²) LLM cost growth. |
| NFR-06 | Scalability | The API shall scale to the request volumes/rate limits agreed with third-party/pilot consumers. |
| NFR-07 | Reliability | Retry failed LLM API calls (e.g., up to 3x with exponential backoff) before marking a classification failed; handle extraction/embedding/vector-search failures gracefully with actionable status. |
| NFR-08 | Reliability | Meet an agreed production uptime target (e.g., 99.5%) consistent with IT/DevOps support expectations. |
| NFR-09 | Reliability | Provide automated backup and recovery for requirement data and audit logs. |
| NFR-10 | Security | All requirement data shall be encrypted at rest and in transit (TLS 1.2+). |
| NFR-11 | Security | Enforce role-based access control tied to authenticated identity (JWT/SSO/LDAP) so users see only authorized projects/requirements/workspaces. |
| NFR-12 | Security | Protect credentials and external AI-service API keys from source-control and client-side exposure. |
| NFR-13 | Security | All access to "protected" compliance-critical requirements shall be logged for audit purposes. |
| NFR-14 | Compliance & Data Residency | Support deployment/hosting configurations satisfying data residency requirements; capable of complying with GDPR/HIPAA-style frameworks, incl. retention and right-to-erasure. |
| NFR-15 | Usability | Clarification questions and flag explanations shall be understandable to a QA engineer or BA without needing to know the underlying AI/NLP model. |
| NFR-16 | Usability | Dashboards and reports shall be tailorable to each stakeholder group's technical literacy (simplified executive view vs. detailed BA view). |
| NFR-17 | Explainability | Every AI-generated finding shall carry evidence/rationale and be clearly distinguishable from human-authored/approved information. |
| NFR-18 | Maintainability | Ambiguity/dependency detection criteria shall be configurable without code changes or redeployment; new SRS input formats addable via a modular parser architecture. |
| NFR-19 | Maintainability | Architecture shall separate ingestion, embedding, classification, and presentation into independently deployable modules/services. |
| NFR-20 | Interoperability | Integrations with third-party tools shall use standard, documented protocols/APIs to minimize custom integration effort. |
| NFR-21 | Accuracy / Trustworthiness | False-positive rate for conflict/duplicate detection shall remain below an agreed threshold, validated against a labeled benchmark set (precision/recall/F1). |
| NFR-22 | Accuracy / Trustworthiness | The confidence-scoring mechanism shall be calibrated and periodically re-validated against user feedback. |
| NFR-23 | Portability | The system shall run identically in local development and production via Docker Compose / containerized deployment. |

## 3. Domain Requirements (DR)

| ID | Requirement |
|---|---|
| DR-01 | The system shall recognize and classify requirement relationships using the four standard categories established in requirements-engineering literature — Conflicting, Duplicate, Ambiguous, and Dependent — not an arbitrary or ad hoc taxonomy. |
| DR-02 | The system shall be able to process SRS documents structured according to common industry templates (e.g., IEEE 830 / ISO/IEC/IEEE 29148-style sections). |
| DR-03 | The system shall preserve unique requirement identifiers present in the source document (e.g., REQ-001, FR-12) rather than regenerating its own numbering scheme. |
| DR-04 | The system shall not silently delete, merge, or alter a requirement's original text; any suggested resolution must be presented for human approval — automated tools assist but do not replace human sign-off. |
| DR-05 | Requirements explicitly marked compliance-critical or regulatory (e.g., HIPAA, GDPR) shall be exempt from automatic duplicate-removal suggestions and routed to mandatory manual review instead. |
| DR-06 | The system shall support bidirectional traceability — tracing a flagged finding back to the exact source requirement(s) and document version it came from. |
| DR-07 | Ambiguity detection shall be grounded in recognized linguistic ambiguity patterns (e.g., vague quantifiers like "fast" without measurable acceptance criteria), not generic LLM judgment alone. |
| DR-08 | The system shall maintain a full change history for every requirement, consistent with configuration-management practice, so any resolved conflict can be audited later. |
| DR-09 | A conflict exists when two or more requirements cannot reasonably be satisfied together under the same stated context; textual/semantic similarity alone is insufficient evidence of conflict or duplication. |
| DR-10 | Semantic similarity search is a retrieval/filtering mechanism used to generate candidate pairs; it is not itself the business definition of duplication, conflict, ambiguity, or dependency. |
| DR-11 | Requirements may originate from different stakeholder groups; stakeholder provenance shall be preserved and is relevant when analyzing conflicts, priorities, dependencies, and resolution paths. |
| DR-12 | Compliance and regulatory rules are scenario-dependent and shall not be assumed unless the analyzed SRS or engagement explicitly identifies the applicable regulation or contractual constraint. |

## 4. Traceability Notes

- FR-21 and NFR-13 jointly satisfy the Legal/Compliance requirement that protected requirements are never auto-flagged, merged, or removed without manual sign-off (DR-04, DR-05).
- FR-13, FR-18, NFR-21, and NFR-22 together answer the Business Analysts' elicitation question of what would make them trust an automated flag without re-checking: a visible confidence score plus a periodically re-validated feedback loop.
- FR-16, FR-17, and FR-18 operationalize the Architects' JAD-session outcome: shared, adjustable definitions of "ambiguous" and "dependent," plus a way to suppress false-positive-prone types.
- FR-40 and NFR-06/NFR-20 respond to Third-Party API Consumer feedback on response format, client libraries, and rate limits — captured second-hand while that elicitation thread is still ongoing.
- FR-41 is intentionally lightweight (survey/feedback mining only), consistent with End Customers being too indirect and numerous for direct interviews.
- NFR-05 and DR-10 jointly encode the embedding-pre-filter architectural decision as both a performance requirement and a domain rule, so it cannot be quietly abandoned under schedule pressure.

## 5. Stakeholder Elicitation Summary

10 stakeholder groups were identified, each matched to an elicitation technique. 8 are complete; End Customers and Third-Party API Consumers are ongoing by design, since both rely on feedback-mining/pilot channels that only become available once a working system exists to pilot.

| Stakeholder | Technique | Status |
|---|---|---|
| Business Analysts / Requirements Engineers | Job Shadowing / Observation | Complete |
| Project Managers | Structured Interviews | Complete |
| Software Architects / Senior Developers | JAD Sessions | Complete |
| Client / Product Owner | Interviews + Document Analysis | Complete |
| QA / Test Engineers | Prototyping (low-fidelity mockups) | Complete |
| Executive Sponsor / Budget Holder | High-level interviews + surveys | Complete |
| Legal / Compliance Team | Document Analysis (regulatory standards) | Complete |
| IT / DevOps / System Administrators | — (see Lab 6 for technique) | Complete |
| End Customers (Indirect) | Feedback mining / surveys | Ongoing |
| Third-Party API Consumers | Pilot feedback channel | Ongoing |
