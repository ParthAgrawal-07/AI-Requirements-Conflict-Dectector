// Clickable prototypes for the US-22 usability sessions (Abhijeet — Sprint 0, throwaway).
// Static data from the design boards; nothing here talks to the API. Delete this folder once the
// real screens exist (join: S1, composer: S3, issue and change request: S4).

import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";

function Frame({ title, next, children }: { title: string; next?: string; children: ReactNode }) {
  return (
    <div className="page grid-paper" style={{ minHeight: "100%" }}>
      <div className="eyebrow">Prototype · not connected to data</div>
      <h1>{title}</h1>
      {children}
      <p style={{ marginTop: 32 }}>
        <Link to="/prototypes">All prototypes</Link>
        {next && (
          <>
            {" · "}
            <Link to={next}>Next screen →</Link>
          </>
        )}
      </p>
    </div>
  );
}

export function PrototypeIndex() {
  return (
    <Frame title="Prototypes">
      <ol>
        <li>
          <Link to="/prototypes/join">Join with a code</Link>
        </li>
        <li>
          <Link to="/prototypes/composer">Write a requirement (composer)</Link>
        </li>
        <li>
          <Link to="/prototypes/findings">Findings: confidence and evidence (US-07)</Link>
        </li>
        <li>
          <Link to="/prototypes/issue">Issue with AI suggestions</Link>
        </li>
        <li>
          <Link to="/prototypes/change-request">Change request checks</Link>
        </li>
        <li>
          <Link to="/prototypes/map-spike">Map library spike (500 nodes)</Link>
        </li>
      </ol>
    </Frame>
  );
}

export function JoinPrototype() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  return (
    <Frame title="Join with a code" next="/prototypes/composer">
      <div className="card" style={{ padding: 20, maxWidth: 420 }}>
        <label htmlFor="proto-code" className="field">
          Join code
        </label>
        <input
          id="proto-code"
          className="input mono"
          placeholder="K7QM-4XPA"
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <p className="field-hint">You join Mobile Banking as Developer.</p>
        <Button variant="primary" onClick={() => navigate("/prototypes/composer")}>
          Join
        </Button>
      </div>
    </Frame>
  );
}

const PATTERNS = ["Always", "When…", "While…", "If… then", "Where…", "Free text"];

export function ComposerPrototype() {
  const [pattern, setPattern] = useState("When…");
  const [when, setWhen] = useState("the user is inactive for 5 minutes");
  const [system, setSystem] = useState("mobile app");
  const [shall, setShall] = useState("end the user's session and show the sign-in screen");
  return (
    <Frame title="Write a requirement" next="/prototypes/issue">
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24 }}>
        <div className="card" style={{ padding: 20 }}>
          <div className="pill-group" role="group" aria-label="Sentence pattern">
            {PATTERNS.map((item) => (
              <button
                key={item}
                type="button"
                className="pill"
                aria-pressed={pattern === item}
                onClick={() => setPattern(item)}
              >
                {item}
              </button>
            ))}
          </div>
          {[
            ["When", when, setWhen],
            ["the", system, setSystem],
            ["shall", shall, setShall],
          ].map(([label, value, set]) => (
            <div className="field" key={String(label)} style={{ marginTop: 12 }}>
              <label htmlFor={`proto-${label}`} className="mono">
                {String(label)}
              </label>
              <input
                id={`proto-${label}`}
                className="input"
                value={String(value)}
                onChange={(event) => (set as (v: string) => void)(event.target.value)}
              />
            </div>
          ))}
          <div className="card" style={{ padding: 12, borderStyle: "dashed" }}>
            <div className="eyebrow">Preview</div>
            When {when}, the {system} shall {shall}.
          </div>
        </div>
        <aside className="card" style={{ padding: 16 }}>
          <div className="eyebrow">Pre-flight check</div>
          <p>
            <Badge tone="conflict">Likely conflict</Badge> with REQ-014 (High, 0.86). It sets 30
            minutes; this sets 5. Owner: Riya.
          </p>
          <p className="mono muted">412 analyses left this month</p>
        </aside>
      </div>
    </Frame>
  );
}

const OPTIONS = [
  { id: "A", title: "Keep REQ-014, change REQ-031", confidence: 0.71, trade: "Mobile users stay signed in longer." },
  { id: "B", title: "One limit of 10 minutes", confidence: 0.82, trade: "Shorter sessions on the web app too." },
  { id: "C", title: "Two limits", confidence: 0.64, trade: "Two timeouts to build and test." },
];

export function IssuePrototype() {
  const [choice, setChoice] = useState("B");
  return (
    <Frame title="ISS-12 Conflict: REQ-031 vs REQ-014" next="/prototypes/change-request">
      <p>
        <Badge tone="conflict">conflict</Badge> <Badge>high</Badge> · assigned to Arjun and Riya
      </p>
      <fieldset className="card" style={{ padding: 16 }}>
        <legend>
          Suggested solutions <Badge tone="ai">AI</Badge>
        </legend>
        {OPTIONS.map((option) => (
          <label key={option.id} className="card" style={{ display: "block", padding: 12, margin: "8px 0" }}>
            <input
              type="radio"
              name="proto-option"
              checked={choice === option.id}
              onChange={() => setChoice(option.id)}
            />{" "}
            <strong>
              {option.id} · {option.title}
            </strong>{" "}
            <span className="mono muted">{option.confidence}</span>
            <div className="muted">Trade-off: {option.trade}</div>
          </label>
        ))}
        <Link className="btn btn-accent" to="/prototypes/change-request">
          Accept {choice} → open change request
        </Link>
      </fieldset>
    </Frame>
  );
}

const CHECKS: [string, "approved" | "info" | "proposed", string][] = [
  ["Conflicts", "approved", "Resolves the conflict with REQ-031. No new conflicts."],
  ["Duplicates", "approved", "None found."],
  ["Impact", "info", "2 direct (REQ-031, REQ-007), 1 transitive (REQ-009)."],
  ["Protected", "proposed", "REQ-014 is protected. A compliance reviewer must approve."],
];

export function ChangeRequestPrototype() {
  return (
    <Frame title="RCR-34 REQ-014: inactivity timeout 30 → 10 minutes">
      <table className="table card">
        <tbody>
          {CHECKS.map(([name, tone, text]) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              <td>
                <Badge tone={tone}>{tone === "approved" ? "pass" : tone === "info" ? "info" : "needs review"}</Badge>
              </td>
              <td>{text}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <Button disabled>Merge into baseline</Button>{" "}
        <span className="muted">Waiting for 1 required review (Meera, compliance).</span>
      </p>
    </Frame>
  );
}
