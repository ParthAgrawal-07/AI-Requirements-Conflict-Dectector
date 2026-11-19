import { useState } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/Toast";
import type { FindingCategory } from "../findings/api";
import { useRequirements } from "../requirements/api";
import { useRaiseConcern, type Concern } from "./api";

export interface RaiseConcernDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  /** The requirement it is about, when raised from one (a result card, the map). */
  requirementId?: string;
  onRaised?: (concern: Concern) => void;
}

const CATEGORIES: { value: FindingCategory; label: string; pair: boolean }[] = [
  { value: "Conflicting", label: "They conflict", pair: true },
  { value: "Duplicate", label: "They say the same thing", pair: true },
  { value: "Dependent", label: "One depends on the other", pair: true },
  { value: "Ambiguous", label: "The wording is ambiguous", pair: false },
  { value: "Incomplete", label: "Information is missing", pair: false },
];
const SEVERITIES = ["low", "medium", "high"] as const;

/** Raise a concern (US-56, FR-97): a problem a person sees, recorded as a finding with a Person
 *  badge and an issue to discuss it — also when the analysis did not report it. */
export function RaiseConcernDialog({ open, onClose, projectId, requirementId, onRaised }: RaiseConcernDialogProps) {
  const notify = useToast();
  const raise = useRaiseConcern(projectId);
  const requirements = useRequirements(projectId, { limit: 200, offset: 0 });
  const [category, setCategory] = useState<FindingCategory>("Conflicting");
  const [first, setFirst] = useState(requirementId ?? "");
  const [second, setSecond] = useState("");
  const [explanation, setExplanation] = useState("");
  const [reference, setReference] = useState("");
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>("medium");
  const pair = CATEGORIES.find((c) => c.value === category)?.pair ?? true;
  const options = requirements.data?.items ?? [];
  const ready = Boolean(first) && (!pair || (Boolean(second) && second !== first)) && explanation.trim().length >= 10;

  const choose = (value: string, onChange: (value: string) => void, label: string, exclude?: string) => (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} required>
        <option value="">Choose a requirement…</option>
        {options
          .filter((r) => r.requirement_id !== exclude)
          .map((r) => (
            <option key={r.requirement_id} value={r.requirement_id}>
              {r.source_req_id ?? "Unnumbered"} — {r.body.length > 60 ? `${r.body.slice(0, 59)}…` : r.body}
            </option>
          ))}
      </select>
    </label>
  );

  return (
    <Drawer open={open} onClose={onClose} title="Raise a concern">
      <form
        className="form-stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (!ready) return;
          raise.mutate(
            {
              category,
              requirement_ids: pair ? [first, second] : [first],
              explanation: explanation.trim(),
              external_ref: reference.trim() || undefined,
              severity,
            },
            {
              onSuccess: (concern) => {
                notify(
                  `${concern.issue_key} opened${concern.ai_miss ? " — the analysis had not reported this" : ""}`,
                  "success",
                );
                onRaised?.(concern);
                onClose();
              },
              onError: (error) => notify(error instanceof ApiError ? error.message : "Could not raise it", "error"),
            },
          );
        }}
      >
        <p className="muted small">
          Your concern is recorded as a finding by a person, shown with a Person badge, and opens an issue for the
          owners.
        </p>
        <label>
          What is wrong?
          <select value={category} onChange={(e) => setCategory(e.target.value as FindingCategory)}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        {choose(first, setFirst, pair ? "First requirement" : "Requirement")}
        {pair && choose(second, setSecond, "Second requirement", first)}
        <label>
          Explain it
          <textarea
            rows={3}
            minLength={10}
            maxLength={4000}
            required
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
          />
        </label>
        <label>
          What it is based on <span className="muted small">(optional, e.g. “Contract §7.2”)</span>
          <input maxLength={200} value={reference} onChange={(e) => setReference(e.target.value)} />
        </label>
        <label>
          Severity
          <select value={severity} onChange={(e) => setSeverity(e.target.value as (typeof SEVERITIES)[number])}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <div className="row-actions">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!ready} loading={raise.isPending}>
            Raise concern
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
