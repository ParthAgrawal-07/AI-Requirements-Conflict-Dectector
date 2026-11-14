// US-22 session prototype (Abhijeet — Sprint 2): the real finding card with static data, so
// sample users judge the actual design (task 1 of docs/usability/s2-sessions.md). No API calls.

import { Link } from "react-router-dom";
import { FindingCard } from "../findings/FindingCard";
import { highlight, type Finding } from "../findings/api";

const SAMPLES: Finding[] = [
  {
    id: "f1",
    project_id: "p",
    source: "AI",
    category: "Conflicting",
    status: "flagged",
    severity: "high",
    confidence: 0.86,
    confidence_percent: 86,
    low_confidence: false,
    explanation: "REQ-014 and REQ-031 set different inactivity limits for the same sessions.",
    evidence_spans: [
      { requirement_id: "r14", label: "REQ-014", quote: "30 minutes", start: 28, end: 38 },
      { requirement_id: "r31", label: "REQ-031", quote: "5 minutes", start: 30, end: 39 },
    ],
    requirements: [
      { id: "r14", label: "REQ-014", body: "Sessions shall expire after 30 minutes of inactivity.", state: "Approved", is_protected: false, origin: "document", section_heading: "3.1 Authentication and Sessions", location: "page 4", document_id: "d", origin_message_id: null },
      { id: "r31", label: "REQ-031", body: "When the user is inactive for 5 minutes, the app shall log the user out.", state: "Proposed", is_protected: false, origin: "post", section_heading: null, location: null, document_id: null, origin_message_id: "m" },
    ],
    dependency_direction: null,
    vague_terms: [],
    missing_information: [],
    context_version: 1,
    prompt_version: "v2",
    analysis_run_id: null,
    created_at: "2026-11-01T10:00:00Z",
  },
  {
    id: "f2",
    project_id: "p",
    source: "AI",
    category: "Ambiguous",
    status: "flagged",
    severity: null,
    confidence: 0.46,
    confidence_percent: 46,
    low_confidence: true,
    explanation: "“Promptly” has no measurable bound. Vague wording: “promptly”.",
    evidence_spans: [{ requirement_id: "r7", label: "REQ-007", quote: "promptly", start: 30, end: 38 }],
    requirements: [
      { id: "r7", label: "REQ-007", body: "The system shall notify users promptly when a document is shared.", state: "Approved", is_protected: false, origin: "document", section_heading: "3.3 Documents and Uploads", location: "page 5", document_id: "d", origin_message_id: null },
    ],
    dependency_direction: null,
    vague_terms: ["promptly"],
    missing_information: [],
    context_version: 1,
    prompt_version: "v2",
    analysis_run_id: null,
    created_at: "2026-11-01T10:00:00Z",
  },
];

export function FindingsPrototype() {
  return (
    <div className="page grid-paper" style={{ minHeight: "100%" }}>
      <div className="eyebrow">Prototype · not connected to data</div>
      <h1>Findings</h1>
      <p className="muted">Task: could you write a test case from each finding?</p>
      <div className="finding-list">
        {SAMPLES.map((finding) => (
          <div key={finding.id}>
            <FindingCard finding={finding} />
            <div className={finding.requirements.length === 2 ? "finding-sides two" : "finding-sides"}>
              {finding.requirements.map((requirement) => (
                <section key={requirement.id} className="finding-side">
                  <h3 className="mono">{requirement.label}</h3>
                  <p className="finding-text">
                    {highlight(
                      requirement.body,
                      finding.evidence_spans.filter((span) => span.requirement_id === requirement.id),
                    ).map((part, index) => (part.marked ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>))}
                  </p>
                  <span className="muted">{requirement.section_heading ?? "From a post in #mobile-app"}</span>
                </section>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p style={{ marginTop: 32 }}>
        <Link to="/prototypes">All prototypes</Link>
      </p>
    </div>
  );
}
