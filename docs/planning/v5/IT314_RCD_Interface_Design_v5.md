# Interface Design

**How people join, write, change, review and watch requirements — AI Requirements Conflict Detector (collaborative workspace scope)**

| | |
|---|---|
| **Scope** | Every screen needed for the MVP stories, with wireframes, behaviour and the stories each one serves |
| **Companions** | `IT314_RCD_Scope_Extension_v5.md` (why), `IT314_RCD_Requirements_Spec_v5.md` (FR-77 to FR-93), `IT314_RCD_Design_Update_v5.md` (APIs and events behind each screen) |
| **Owners** | Pranshu (shell, map, composer, requirements, channels, dashboard) · Abhijeet (findings, change requests, issues, notifications, members, compliance) |
| **Revision 3** | Adds the AI suggestion panel (§8a) and the written Changes panel beside the map (§9) |
| **Revision 4** | Trust elements (§8b): source badges, Raise a concern, decision owner, findings delta, agreement status, honest clean results, structured feedback, approved-only export with open-items report, decision rules |
| **Revision 5** | Project setup wizard with the compulsory context step and the Setup banner (§8c); Updated SRS screen: readiness checklist, section review, fidelity check, publish and export (§8d) |
| **Status** | Proposal for Sprint 0. Wireframes are low fidelity on purpose: US-22 tests them with sample users before they are built |

---

## 1. Design Principles

| # | Principle | What it means on screen |
|---|---|---|
| 1 | **Structure beats free text** | Requirements are written in EARS sentence templates with named slots, not a blank text box |
| 2 | **Feedback before commitment** | Lint as you type, similar requirements as you type, a pre-flight check and a map preview before anything is submitted |
| 3 | **One home per object** | A requirement, an issue and a change request each have one page or drawer; everything else links to it |
| 4 | **Familiar where possible** | Channels look like Slack; issues and change requests look like GitHub. People already know both |
| 5 | **AI proposes, people decide** | Every AI output carries an "AI" label and confidence; nothing AI-written is applied without a human action, and every response (accept, edit, reject, regenerate) is recorded (DR-04, DR-20) |
| 6 | **Never colour alone** | Severity, category and state use colour **and** shape, icon or text (NFR-29) |
| 7 | **Keyboard-first** | `Ctrl/⌘ K` command palette, `N` new requirement, `C` comment, `?` shortcuts list |
| 8 | **Show only allowed actions** | Buttons a member lacks permission for are hidden, not disabled, except where seeing them explains the process (e.g. a greyed **Merge** with "needs 1 more approval") |
| 9 | **Every picture also in words** | Whatever the map shows, the Changes panel and the drawer also say in sentences |

## 2. Information Architecture

```
Workspace (switcher, top-left)
└── Project       ← new projects open the setup wizard; "Setup" banner until context is confirmed
    ├── Map            ← default landing tab: the live requirements map
    ├── Requirements   ← table of all requirements, filters, bulk view
    ├── Issues         ← ISS-n, GitHub-style list
    ├── Changes        ← RCR-n, pull-request-style list
    ├── Channels       ← #general, #mobile-app, … (also in the sidebar)
    ├── Baselines      ← snapshots, comparison, and the Updated SRS (generate, review, publish, export)
    └── Insights       ← dashboard and analytics
Global: Inbox (bell) · Command palette (Ctrl K) · Profile · Workspace settings (members, roles, join codes)
Right side: Requirement drawer — opens over any tab when a requirement is selected
```

## 3. Application Shell

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣ Acme Bank ▾   Mobile Banking ▾        [ Search or run a command…  Ctrl K ]   🔔 3  (RK) │
├──────────────┬─────────────────────────────────────────────────────────────────────────┤
│ PROJECT      │  Map   Requirements   Issues 4   Changes 2   Baselines   Insights        │
│  Map         ├─────────────────────────────────────────────────────────┬───────────────┤
│  Requirements│                                                         │ REQ-014  ✓Appr│
│  Issues    4 │                                                         │ Session time- │
│  Changes   2 │            (tab content — e.g. the live map)            │ out after 30… │
│              │                                                         │ Owner: Riya   │
│ CHANNELS     │                                                         │ [Propose chg] │
│  # general   │                                                         │ [Open issue]  │
│  # mobile-app│                                                         │ ☆ Watch  👍 4 │
│  # security •│                                                         │ Overview│Find…│
│              │                                                         │               │
│ [+ New req ] │                                                         │  (drawer)     │
└──────────────┴─────────────────────────────────────────────────────────┴───────────────┘
```

- **+ New requirement** is always visible in the sidebar (also `N`, `/req` in a channel, or double-click on empty map space).
- Unread dots on channels; counts on Issues and Changes show items **assigned to me or awaiting my review**.

## 4. Joining a Workspace (US-25, US-49; FR-44, FR-77)

### 4.1 Creating a code (Owner, Admin, Project Manager)

```
Workspace settings › Join codes                                       [ + New join code ]
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ New join code                                                                         │
│  Project access   [ Mobile Banking ▾ ]  (or "Workspace only")                         │
│  Default role     [ Developer ▾ ]        Owner and Admin cannot be granted by a code  │
│  Expires          ( ) 1 day  (•) 7 days  ( ) 30 days                                  │
│  Max uses         [ 20 ]                                                              │
│  [✓] Require approval before joining                                                  │
│                                                         [ Cancel ]  [ Create code ]   │
└───────────────────────────────────────────────────────────────────────────────────────┘
  Created:   K7QM-4XPA   ⧉ Copy code   ⧉ Copy link   (shown in full only now)
  Active codes:  …4XPA · Developer · 3/20 used · expires 22 Oct · [Revoke]
```

### 4.2 Joining (anyone with the code)

1. **Sign up or sign in** → "Enter a join code" (or the link fills it in).
2. If approval is required, the screen says *"Request sent to Mobile Banking's managers"*, and the PM sees it in **Members › Requests** with Approve (role picker) / Deny.
3. On entry the member lands in `#general` with a **3-step checklist**: *Read the project brief* · *Explore the map* · *Write your first requirement* (NFR-31).

### 4.3 Members and roles

- **Members** table: name, role (editable inline by those with `members.manage`), projects, joined, last active, *Remove*.
- **Roles** page: the 9 default roles (read-only) and **+ Custom role**, a checklist of permissions grouped as *Workspace · Requirements · Review · Governance*, with a live sentence "This role can propose requirements, review change requests, but not merge."

## 5. The Requirement Composer (US-30, US-51; FR-55, FR-81 to FR-83, FR-93)

The composer is the most important screen: good requirements written at the source mean fewer conflicts later.

### 5.1 Layout

```
┌ New requirement ─────────────────────────────────────────────── Draft saved ✓ ──── ✕ ┐
│ Template:  [Always] [When…] [While…] [If…then] [Where…]          (EARS patterns)      │
│                                                                                        │
│  When  [ the user is inactive for 5 minutes        ]                                   │
│  the   [ mobile app                                ]  shall                            │
│        [ log the user out                          ]                                   │
│                                                                                        │
│  Preview: "When the user is inactive for 5 minutes, the mobile app shall log the user  │
│            out."                                       [ ✨ Improve wording (AI) ]     │
│ ──────────────────────────────────────────────────────────────────────────────────── │
│  Type [Functional ▾]  Priority [Must ▾]  Group [Security ▾]  Owner [me ▾]  Tags [+]    │
│  Rationale  [ RBI guideline on idle sessions…                                    ]     │
│  Acceptance criteria   Given [ a logged-in user ]  When [ no input for 5 min ]         │
│                        Then  [ the session ends and the login screen is shown ]  [+]   │
│  Links      [ depends on ▾ ] [ REQ-… ]                                          [+]    │
├──────────────────────────────── side panel ────────────────────────────────────────── │
│  QUALITY  ●●●●○  Good                                                                  │
│   ✓ Has an actor and a measurable trigger                                              │
│   ⚠ "log out" — consider "end the session" (consistent with REQ-002)                   │
│  SIMILAR REQUIREMENTS  (as you type)                                                   │
│   REQ-014  Session timeout after 30 minutes of inactivity      0.88  [view]            │
│   REQ-022  Re-authenticate before payments                     0.71  [view]            │
│  PRE-FLIGHT CHECK          [ Run check ]  uses 1 of 412 remaining analyses this month  │
│   ✗ Likely conflict with REQ-014 (High)   ⓘ 1 dependency                              │
│   [mini-map: ghost node with a red edge to REQ-014]                                    │
├──────────────────────────────────────────────────────────────────────────────────────── │
│                                   [ Save draft ]   [ Propose requirement  Ctrl ⏎ ]     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Behaviour

| Element | Behaviour | Cost |
|---|---|---|
| **EARS templates** | Five chips: *Always* (ubiquitous), *When* (event), *While* (state), *If…then* (unwanted behaviour), *Where* (optional feature). Each shows labelled slots; *Free text* is available but gets a lint hint (DR-18) | None |
| **Live lint** | Runs 300 ms after typing stops (NFR-34). Uses the same pattern catalogue as DR-07: vague quantifiers, weak verbs ("support", "handle"), passive voice without actor, missing number or unit, "and/or", "etc.", multiple "shall"s (suggests splitting). Underlines in the text plus a list in the side panel | None (deterministic) |
| **Quality meter** | 5 dots from the lint results; advisory only, never blocks submission | None |
| **Similar requirements** | After 800 ms of no typing, embeds the draft and shows the top 3 by similarity, like "similar questions" on Stack Overflow | Embedding only, no LLM |
| **Pre-flight check** | On click: runs the incremental analysis on the draft in **dry-run mode** (nothing saved), shows findings and a ghost node on a mini-map | Counts against the LLM budget; the remaining count is shown |
| **Improve wording (AI)** | Suggests an EARS rewrite in a diff; *Accept* replaces the slots, *Dismiss* keeps the original. Labelled "AI suggestion" | 1 LLM call |
| **Draft autosave** | Every 5 s to the server as a private draft | None |
| **Propose** | Creates a Proposed requirement, posts a requirement card to the chosen channel (default: the group's channel) and starts live analysis; the composer closes and the map pulses the new node | Normal analysis run |

### 5.3 Other entry points

- `/req` in a channel opens the composer pre-filled with the message being written.
- **Promote to requirement** on a chat message (chat detection, US-32) opens it pre-filled with that message.
- **Create requirement** from an issue pre-links the issue.

## 6. The Requirement Drawer (US-53, US-42, US-36; FR-80)

```
┌ REQ-014 ─────────────────────────────────────────── ✓ Approved · v2 · Must ─ ✕ ┐
│ "When the user is inactive for 30 minutes, the system shall end the session."  │
│ Owner Riya (Security) · Group Security · Protected ⚑ · Watching ☆              │
│ 👍 Support 4   👎 Oppose 1        2 open issues · 1 open change request        │
│ [ Propose change ] [ Open issue ] [ Link ▾ ] [ ··· ]                            │
│                     ··· → Request ownership · Mark implemented · View on map    │
│                          · Copy link · Export                                  │
├ Overview │ Findings 2 │ Issues 2 │ Changes 1 │ Discussion 6 │ History ─────────┤
│ Overview: rationale, acceptance criteria, links (human ⟶ / AI-detected ⇢),     │
│           origin (document SRS-v1 §4.2), linked work items                     │
│ History : timeline — v1 imported · finding F-88 · ISS-12 opened · RCR-34 …     │
└────────────────────────────────────────────────────────────────────────────────┘
```

- Actions appear only if the member has the permission (§3.1 of `IT314_RCD_Scope_Extension_v5.md`).
- **Support / Oppose** opens a one-line reason box; the tally is advisory (DR-17).
- **Link** asks for type (*depends on*, *refines*, *related to*) and target; human links show as solid arrows, AI-detected relationships as dashed.

## 7. Changing a Requirement: Change Editor and Change Request Page (US-33, US-34, US-35, US-52; FR-62 to FR-66, FR-88, FR-89)

### 7.1 Change editor (opens from **Propose change**)

```
┌ Propose a change to REQ-014 (base v2) ─────────────────────────────────────────── ✕ ┐
│ Kind  (•) Modify   ( ) Deprecate                                                     │
│ ┌ Composer, pre-filled with the current text (same templates and lint) ───────────┐ │
│ │ When the user is inactive for [ 10 ] minutes, the system shall end the session. │ │
│ └──────────────────────────────────────────────────────────────────────────────────┘ │
│ Diff:  When the user is inactive for ~~30~~ **10** minutes, the system shall end …  │
│ Reason (required)  [ Audit finding A-17: idle sessions must end within 10 minutes ] │
│ Resolves  [ ISS-12 × ]                                                              │
│ Reviewers (auto)  Riya (owner) · Arjun (owner of REQ-031, direct conflict)  [+ add] │
│ Checks (pre-flight)  ✓ resolves 1 conflict   ⓘ 3 affected   ⚑ protected → compliance │
│                                       [ Save as draft ]  [ Open change request ]     │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Change request page (like a pull request)

```
RCR-34  REQ-014: inactivity timeout 30 → 10 minutes                    ● Open · Risk Medium
Proposed by Arjun · base v2 · Resolves ISS-12
┌ Conversation │ Diff │ Checks 6 │ Map preview ───────────────────────┬──────────────────────┐
│ CHECKS                                                              │ Reviewers            │
│  ✓ Conflicts      resolves conflict with REQ-031                    │
│                   (a failing check shows 💡 suggested fixes, §8a)   │  ✓ Riya   approved   │
│  ✓ Duplicates     none                                              │  ○ Meera  requested  │
│  ⚠ Ambiguity      none new                                          │    (compliance)      │
│  ⓘ Impact         2 direct (REQ-031, REQ-040), 1 transitive          │  ○ Dev    optional   │
│  ⓘ Work touched   2 items · 8 pts                                   │ Policy: 2 of 3 ▮▮▯   │
│  ⚑ Protected      compliance reviewer required                      │ Labels: security     │
│  Risk: Medium  (rule: 3–10 requirements affected)                   │ Votes:  👍 5  👎 0     │
│  AI summary  ⓘAI  "Shortening the timeout resolves the conflict…"   │ Linked: ISS-12       │
│                                                                     │                      │
│  [ Merge into baseline ]  disabled — waiting for 1 required review  │ ☆ Watch              │
└─────────────────────────────────────────────────────────────────────┴──────────────────────┘
```

| Tab | Content |
|---|---|
| **Conversation** | Description, comments, review events, system events ("checks re-run", "needs update") in time order |
| **Diff** | Word-level diff of the statement and every changed field; reviewers select words to add **inline review comments** |
| **Checks** | The consequence report as checks, each with ✓ / ⚠ / ✗ / ⓘ icon **and** text; expand for details and links |
| **Map preview** | The map with the change as a ghost overlay: edges that disappear fade out, new edges glow |

| Review action | Effect |
|---|---|
| **Approve** | Counts toward the policy if the reviewer is eligible (never the proposer) |
| **Request changes** | Blocks merge until the proposer updates and that reviewer re-reviews |
| **Comment** | No effect on the policy |

- **Merge** is enabled only when the policy is satisfied and the checks are current. It is shown to members with the merge permission, and greyed out with the reason otherwise (§1, principle 8).
- **Needs update** banner: *"REQ-014 changed to v3 after this request was opened"*, with a three-way view (base v2 · current v3 · proposed) and **Update request**, which re-runs the checks.

## 8. Issues (US-52; FR-86, FR-87)

```
Issues   [ Open 4 ]  Closed 19     Filters: Label ▾  Assignee ▾  Requirement ▾   [ New issue ]
 ● ISS-12  Conflict: REQ-031 vs REQ-014      conflict · high   👤 Riya, Arjun   🤖 auto   2 h
 ● ISS-11  Is "statement" the PDF or the CSV?  question         👤 Meera                1 d
```

**An auto-opened conflict issue:**

```
ISS-12  Conflict: REQ-031 vs REQ-014                          ● Open   conflict · high · 🤖 auto
┌───────────────────────────────┬───────────────────────────────┐
│ REQ-031 (Arjun, Proposed)     │ REQ-014 (Riya, Approved v2)   │
│ When the user is inactive for │ When the user is inactive for │
│ **5** minutes, the app shall  │ **30** minutes, the system    │
│ log the user out.             │ shall end the session.        │
└───────────────────────────────┴───────────────────────────────┘
ⓘAI  Both requirements set different inactivity limits for the same session. (confidence 0.86)
Clarification question: Which inactivity limit applies to the mobile app: 5 or 30 minutes,
and does it differ for payment screens?
💡 Suggested solutions ⓘAI   (panel from §8a)   A · B (Riya ✓, Arjun ✓) · C
Next steps:  [ Accept B → change request ]  [ Propose change to REQ-014 ]  [ Propose change to REQ-031 ]  [ Not a conflict… ]
```

- **Not a conflict…** opens the finding review (dismiss with a reason; requires the finding-review permission).
- An issue closes automatically when a linked change request merges with *Resolves ISS-12*, or when its finding is dismissed or resolved (SX-18).

## 8a. AI Suggestion Panel (US-45; FR-68, FR-94)

Appears wherever a finding appears: the finding detail, the analysis result card (collapsed as "💡 3 suggested fixes"), the conflict issue, and next to a failing check on a change request.

```
┌ 💡 Suggested solutions  ⓘAI ─────────────────────── for F-88 · Conflicting · High ─┐
│ ( ) A  Keep REQ-014 (30 min); change REQ-031 to match.                       0.71 │
│        Trade-off: mobile users stay logged in longer.                              │
│ (•) B  "When the user is inactive for 10 minutes, the system shall end the         │
│        session."  Applies to both; replaces REQ-014 and withdraws REQ-031.   0.82 │
│        Trade-off: shorter sessions on the web app too.     Riya ✓  Arjun ✓          │
│ ( ) C  30 min generally; 5 min on payment screens (two requirements).       0.64 │
│        Trade-off: two timeouts to implement and test.                              │
│                                                                                    │
│ Diff for B:  When the user is inactive for ~~30~~ **10** minutes, …                │
│                                                                                    │
│ [ Accept B → open change request ]  [ Edit B first ]  [ Defer — not decided yet ]  │
│ Reject because:  changes the intended meaning · infeasible · AI missed context     │
│ [ ↻ Regenerate with instruction: "keep 30 minutes for the web app"           ]     │
│ Suggestions are proposals. Accepting one does not mean it is correct.              │
└────────────────────────────────────────────────────────────────────────────────────┘
```

| Element | Behaviour |
|---|---|
| **Options** | Up to three, each with wording (as a diff against the current text), trade-off and confidence; category-specific (see `IT314_RCD_Scope_Extension_v5.md` §3.6) |
| **`[TBD — confirm]`** | Values the AI had to invent are shown highlighted and must be replaced before the change request can be opened |
| **Preference marks** | On a two-owner conflict issue, each owner can mark a preferred option; marks are shown to everyone |
| **Accept** | Opens the change editor (§7.1) pre-filled with the option, the finding and issue linked, and "Suggested by AI, accepted by Riya" recorded |
| **Edit first** | Opens the same editor with the option editable; the final text is stored as "edited" feedback |
| **Reject** | Requires one structured reason: changes the intended meaning, infeasible, or AI missed important context (free text optional) |
| **Defer** | Records "team has not decided"; the suggestion stays visible on the issue |
| **Regenerate** | Takes a one-line instruction; new options replace the old ones, which stay in the history |
| **Transparency** | A "History" link lists earlier suggestions and what people chose; the panel never claims the AI learns from these choices |

## 8b. Trust Elements (revision 4; US-56 to US-59)

These elements appear across screens; they make the product honest about what it knows and who decides.

| Element | Where | Behaviour |
|---|---|---|
| **Source badge** `AI` · `Rule` · `Person` | Every finding, issue row, result card, map badge | Icon + text; filter by source in Issues and Requirements |
| **Raise a concern** | Requirement drawer, map node menu, message menu, every clean result | Form: category (five + Other), involved requirements, explanation, external reference (e.g. "Contract §7.2"). Creates a Person finding + issue with its decision owner |
| **Decision owner line** | Issue header, change request header and reviewer list | "Decides: Meera (Compliance) — rule *Protected requirements*"; links to the rule |
| **Honest clean result** | Result cards, pre-flight, Checks tab | "No issues detected by analysis — analysis can miss conflicts. [Raise a concern]". Never "verified" or "safe" |
| **Findings delta** | Top of the Checks tab | Four groups with counts: Resolved · New · Still open · Must re-run before approval |
| **Agreement status** | Change request merge bar | A checklist of FR-98 conditions with ✓ / ✗ and text: base version current, checks current for revision *n*, decision owner approved revision *n*, required reviewers, no open High finding. Merge stays disabled until all pass; earlier-revision approvals are shown struck through as *dismissed* |
| **Structured feedback** | AI suggestion panel | Accept · Edit then accept · Reject (changes the intended meaning / infeasible / AI missed context) · Defer · Regenerate. No thumbs, no "your choices teach the AI" copy |
| **Excluded-items banner** | Baselines export | "This export contains only approved requirements. Not included: 23 proposed, 7 open findings, 2 open change requests — see the open-items report." with two export buttons |
| **Decision rules** | Workspace settings › Decision rules tab | Table of rules (match → decision owner → required reviewers), most specific first, default rule pinned at the bottom |

## 8c. Project Setup and Context (revision 5; US-24, US-60; FR-103 to FR-105)

Creating a project opens a four-step wizard: **1 Name · 2 Context · 3 Settings · 4 Invite**. Step 2 cannot be skipped.

```
┌ New project ─ Mobile Banking ───────────────────────── 1 ── 2 ── 3 ── 4 ┐
│ PROJECT CONTEXT (required)  The AI uses this to understand every requirement│
│ ( ) Upload initial SRS   ( ) Write a brief   (•) Both                      │
│ ┌──────────────────────────────────────────┐                               │
│ │ Mobile_Banking_SRS_v0.9.docx  ✓ 142 req.   │  Import as: (•) baseline ( ) proposals │
│ └──────────────────────────────────────────┘                               │
│ Purpose*      [AI-drafted] A mobile app that lets retail customers…  ✓ Confirm  ✎ │
│ Scope*        In: accounts, transfers, bill pay · Out: loans, trading ✓ Confirm  ✎ │
│ Actors*       Customer · Support agent · Fraud analyst           ✓ Confirm  ✎ │
│ Environment*  Android 10+, iOS 15+, core banking over REST      ✓ Confirm  ✎ │
│ Glossary      OTP · Beneficiary · Session · + add               (optional)   │
│ Constraints · Quality goals · Regulations · References          (optional)   │
│ 3 of 4 required fields confirmed — analysis starts when all are confirmed   │
│                                                  [ Back ]  [ Continue → ]   │
└────────────────────────────────────────────────────────────────────────────┘
```

- AI-drafted fields carry the `AI-drafted` label until confirmed; editing a field confirms it.
- Until confirmation the project shows a **Setup** banner on every tab: "Analysis is off until the project context is confirmed. [Finish setup]". The composer, upload-for-analysis and Propose change are hidden; channels work.
- **Project settings › Context** shows the current version, its author and date, an **Edit context** button (`project.context`) that asks for a reason, and a version history. After an edit: "Re-run analysis of 12 open findings with the new context? [Re-run] [Later]".
- The finding drawer shows "Analysed with context v3" in its footer.

## 8d. Updated SRS (revision 5; US-61, US-41, US-59; FR-106, FR-107)

**Baselines › Updated SRS** has three states: readiness, review, published.

```
UPDATED SRS · Mobile Banking · from baseline rev 41                    SRS v1.0 published 12 Oct
┌ Readiness ─────────────────────────────┐
│ ✓ No open clarification questions        │
│ ✗ 1 open High finding without accepted risk  ISS-19 ↗ │
│ ✓ No open change requests on included requirements │
│ ✓ No open issues on included requirements   │
│ [ Generate draft ]  (disabled · or PM: Override with reason…) │
└──────────────────────────────────────────┘

REVIEW  SRS v1.1 draft                         7 of 12 sections accepted · Fidelity: not run
┌ Sections ──────────────┐ ┌ 1.2 Scope ──────────────────────────────── AI ────────────┐
│ ✓ 1.1 Purpose           │ │ The app covers retail accounts, transfers and bill payment… │
│ ● 1.2 Scope        AI   │ │                                                              │
│ ✓ 1.3 Definitions       │ │ [ Accept ]  [ Edit ]  [ Regenerate ▾ "shorter, for the client" ] │
│ ✓ 2.x Overall descr.    │ └──────────────────────────────────────────────────────────────┘
│ 🔒 3.1 Functional (118) │   3.x sections are requirement tables inserted by the system:
│ 🔒 3.2 Non-functional (24)│ read-only here; text changes go through change requests.
│ ● A. Changes since v1.0 │
│ ● B. Decisions          │
└─────────────────────────┘
[ Run fidelity check ]  [ Publish SRS v1.1 ]  (needs all sections accepted and a passing check)

PUBLISHED  SRS v1.0 · v1.1      [ Compare v1.0 ↔ v1.1 ]   Export: [ DOCX ] [ PDF ] [ Markdown ]  + Open-items report
```

- Requirement sections (🔒) are generated by the system from the baseline and cannot be edited here; the lock tooltip says why.
- The fidelity check lists failures in words: "REQ-031 missing", "Section 1.2 contains a 'shall' sentence that is not a baseline requirement".
- The excluded-items banner of §8b also appears above the export buttons.

## 9. The Live Requirements Map (US-14, US-50, US-55; FR-84, FR-85, FR-95, FR-96)

```
┌ Map ─────────────────────────────────────────────────────────────────────────────────────┐
│ Layers: [✓] Baseline [✓] Proposed [ ] Preview   Group by: [ Stakeholder group ▾ ]        │
│ Show: [✓] Conflicts [✓] Duplicates [✓] Dependencies [✓] Human links   Search [ REQ-… ]   │
│                                                                                          │
│     ╭─ Security ───────────╮          ╭─ Payments ──────────────╮                         │
│     │  ■REQ-014 ━━✕━━ ▢REQ-031 │      │  ■REQ-022 ──▶ ■REQ-040  │                         │
│     │     ╲                 │       │      ║ duplicate          │                         │
│     │      ▶ ■REQ-002       │       │  ■REQ-041                 │                         │
│     ╰───────────────────────╯       ╰──────────────────────────╯                         │
│                                                                                          │
│  ◉ live · REQ-031 added by Arjun — 1 conflict (2 s ago)                     [⊕][⊖][⤢]     │
│  ├──────●───────────●─────────────────●──────────────▶ now   (v1.0)  (v1.1)   ⟲ replay   │
└──────────────────────────────────────────────────────────────────────────────────────────┘

Changes panel (right side of the map; collapsible; US-55):
┌ CHANGES ─────────────────────────────── Everyone ▾  All kinds ▾ ┐
│ 10:52 Riya merged RCR-34: REQ-014 inactivity limit 30 → 10 min  │
│       (v3). Conflict REQ-031 ↔ REQ-014 resolved. ISS-12 closed. │
│ 10:47 Riya and Arjun both preferred AI option B for ISS-12.     │
│ 10:42 Arjun added REQ-031 (Security, Must). 1 conflict with     │
│       REQ-014 (High, 0.86). ISS-12 opened for Arjun and Riya.   │
│ ──────────────────────────────────────────────────────────────  │
│ [ Summarise changes since ▾ ]  v1.0 · yesterday · my last visit │
│ Since v1.0: 4 added · 2 changed · 1 deprecated · 3 conflicts    │
│ resolved · 2 change requests merged.                            │
│ ⓘAI "Most activity was in Security: the inactivity limit was    │
│ unified at 10 minutes…"                     [ Copy as Markdown ] │
└─────────────────────────────────────────────────────────────────┘
Legend:  ■ approved (solid)  ▢ proposed (dashed)  ◌ preview (ghost)
         ━✕━ conflict (red)  ══ duplicate  ──▶ dependency  ─── human link (grey)   badge = open issues
```

| Feature | Behaviour |
|---|---|
| **Live updates** | Receives `graph.delta` events; new or changed elements pulse for 3 s; a toast and the activity ticker say what happened and who did it |
| **Changes in writing** | Every delta also becomes a sentence in the Changes panel; selecting a sentence highlights its elements, hovering a node filters the panel to it; the panel follows the time slider |
| **Summaries** | "Summarise changes since…" a snapshot, a date or the last visit: computed counts, important changes, optional AI paragraph; copy as Markdown or export |
| **Relationship sentences** | The drawer of a focused node explains each edge in a sentence with its evidence |
| **Stable layout** | Force-directed layout with **persisted positions**; new nodes are placed next to their nearest neighbour; nothing jumps when something else changes |
| **Grouping** | Clusters by stakeholder group, type or owner |
| **Focus mode** | Click a node: neighbours within 1 or 2 hops stay bright, the rest fade; the drawer opens |
| **Preview layer** | Shows a pre-flight draft or an open change request as ghost nodes and edges |
| **Time slider** | Drag to any baseline revision or snapshot; the map replays the state at that point (read-only) |
| **Scale** | Above 300 nodes, low-zoom shows clusters as bubbles with counts; table view is always one click away |
| **Accessibility** | Arrow keys move between connected nodes; every edge has a text equivalent in the drawer; the table view lists the same data |

**Library:** Cytoscape.js (with the fCoSE layout) is recommended for 500+ nodes; React Flow is easier for small graphs. A Sprint 0 spike decides, using 500 nodes and 2,000 edges (NFR-33).

## 10. Channels and Result Cards (US-29, US-31)

```
# mobile-app
 Arjun  10:42   📄 REQUIREMENT  REQ-031 · Proposed · Must · Security
               "When the user is inactive for 5 minutes, the app shall log the user out."
   └ 🤖 Analysis (14 s)  ✗ Conflicting with REQ-014 · High · 0.86   → ISS-12 opened
                         Clarification: Which inactivity limit applies…?   @Riya
                         💡 3 suggested fixes ▸
                         [ View on map ]  [ Open ISS-12 ]
 Riya   10:47   Looking at it — we had an audit finding about this.
```

Requirement cards, change-request cards and analysis cards are distinct message types (`IT314_RCD_Design_Update_v5.md` §4), so they stay readable among chat.

## 11. Inbox and Notifications (US-38)

GitHub-style inbox grouped by reason: **Review requested · Assigned · Mentioned · Watching · Results on my requirements**. Each row links to its subject; *Mark done* and *Mark all read*. The bell shows the unread count, updated live.

## 12. Insights (US-13, US-44)

- **Dashboard tiles:** open findings by category and severity, requirements by state, open change requests by risk, issues open and closed this week, baseline revision.
- **AI feedback:** suggestion acceptance rate per category, top rejection reasons, dismissed findings by category (US-15, US-45).
- **Analytics:** volatility chart, conflict hotspots, the stakeholder-group contention matrix (heat map with numbers in each cell), time from proposal to merge.
- Every number drills down to the filtered list (FR-28).

## 13. Responsive and Accessible

- **Desktop first.** At tablet width the drawer becomes a full-screen sheet; on phones the app supports reading, commenting, voting and reviewing, while the map shows the table view by default.
- **WCAG 2.1 AA** for the core flows (NFR-29): visible focus, 4.5:1 contrast, labelled controls, shape plus colour for every status.

## 14. Screen-to-Story Map

| Screen | Stories | Sprint | Owner |
|---|---|---|---|
| Login, sign-up with code, onboarding checklist | US-19, US-25 | S1 | Pranshu, Abhijeet |
| Project setup wizard, context step, Setup banner, context settings | US-24, US-60 | S1 | Abhijeet |
| Updated SRS (readiness, section review, fidelity, publish, export) | US-61, US-41 | S6 | Pranshu (UI), Bansil |
| Members, roles, join codes | US-25, US-26, US-49 | S1–S2 | Abhijeet |
| Channels and cards | US-28, US-29, US-31 | S2–S3 | Pranshu |
| Composer (templates, fields) | US-30 | S3 | Pranshu |
| Composer (lint, similar, pre-flight, AI wording) | US-51 | S5 | Bansil (wiring), Keval (services) |
| Live map (with one-line written feed) | US-14 | S3 | Abhijeet, Dhavni didi |
| AI suggestion panel | US-45 | S5 | Abhijeet (UI), Madhav, Keval |
| Changes panel and summaries | US-55 | S6 | Pranshu, Dhavni didi, Keval |
| Raise a concern, source badges | US-56 | S4 | Pranshu |
| Decision rules settings, decision owner line | US-57 | S5 | Pranshu |
| Findings delta, agreement status | US-34, US-35 | S4 | Abhijeet |
| Open-items export banner | US-59 | S6 | Bansil |
| Map preview layer and time slider | US-50 | S5 | Pranshu, Dhavni didi |
| Findings and review | US-07, US-08, US-09, US-10 | S2–S4 | Abhijeet |
| Change editor and change request page | US-33, US-34, US-35 | S4 | Abhijeet |
| Issues | US-52 | S4 | Pranshu |
| Requirement drawer, discussion, votes, watch, links | US-36, US-53 | S3, S5 | Pranshu, Abhijeet |
| Inbox | US-38 | S5 | Abhijeet |
| Baselines | US-40, US-41 | S5–S6 | Pranshu |
| Insights | US-13, US-44 | S5–S6 | Pranshu |
