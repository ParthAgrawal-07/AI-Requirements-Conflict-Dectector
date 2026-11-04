import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useDocuments } from "../projects/api";
import { DocumentProgressList, UploadDialog } from "../projects/UploadDialog";
import {
  useProjectContext,
  useSaveContext,
  type BriefField,
  type BriefValues,
  type ProjectContext,
} from "./api";

// One text box per brief column. Lists are edited as text: actors one per line, glossary
// "term: meaning" per line.
type FormKey =
  | "purpose"
  | "scope_in"
  | "scope_out"
  | "actors"
  | "environment"
  | "glossary"
  | "constraints"
  | "quality_goals"
  | "regulations";
export type BriefForm = Record<FormKey, string>;

const FIELD_OF: Record<FormKey, BriefField> = {
  purpose: "purpose",
  scope_in: "scope",
  scope_out: "scope",
  actors: "actors",
  environment: "environment",
  glossary: "glossary",
  constraints: "constraints",
  quality_goals: "quality_goals",
  regulations: "regulations",
};

const LABELS: Record<FormKey, string> = {
  purpose: "Purpose and problem",
  scope_in: "In scope",
  scope_out: "Out of scope",
  actors: "User classes and actors (one per line)",
  environment: "Operating environment and domain",
  glossary: "Glossary (one “term: meaning” per line)",
  constraints: "Constraints and assumptions",
  quality_goals: "Quality goals",
  regulations: "Applicable regulations",
};

const REQUIRED: FormKey[] = ["purpose", "scope_in", "scope_out", "actors", "environment"];
const OPTIONAL: FormKey[] = ["glossary", "constraints", "quality_goals", "regulations"];

export function toForm(values: BriefValues | undefined): BriefForm {
  return {
    purpose: values?.purpose ?? "",
    scope_in: values?.scope_in ?? "",
    scope_out: values?.scope_out ?? "",
    actors: (values?.actors ?? []).join("\n"),
    environment: values?.environment ?? "",
    glossary: (values?.glossary ?? []).map((g) => `${g.term}: ${g.meaning}`).join("\n"),
    constraints: values?.constraints ?? "",
    quality_goals: values?.quality_goals ?? "",
    regulations: values?.regulations ?? "",
  };
}

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Only what the person changed, in the API's shape (editing a field confirms it). */
export function changedValues(form: BriefForm, saved: BriefForm): BriefValues {
  const changes: BriefValues = {};
  for (const key of Object.keys(form) as FormKey[]) {
    if (form[key].trim() === saved[key].trim()) continue;
    if (key === "actors") {
      changes.actors = lines(form.actors);
    } else if (key === "glossary") {
      changes.glossary = lines(form.glossary).map((line) => {
        const at = line.indexOf(":");
        return at > 0
          ? { term: line.slice(0, at).trim(), meaning: line.slice(at + 1).trim() }
          : { term: line, meaning: line };
      });
    } else {
      changes[key] = form[key].trim() || null;
    }
  }
  return changes;
}

function statusOf(context: ProjectContext | undefined, field: BriefField) {
  return context?.fields.find((state) => state.field === field)?.status ?? null;
}

/** Setup wizard (US-24, US-60): the context step cannot be skipped. Upload the initial SRS
 *  (its brief is drafted by AI), write the brief, or both; AI-drafted fields stay labelled until
 *  someone confirms or edits them. Confirming every required field makes the project Active. */
export function SetupWizard() {
  const { workspaceId = "", projectId = "" } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const { can } = usePermissions({ projectId });
  const documents = useDocuments(projectId);
  const processing = (documents.data?.items ?? []).some((doc) =>
    ["queued", "processing"].includes(doc.status),
  );
  const context = useProjectContext(projectId, { poll: processing });
  const save = useSaveContext(projectId);

  const saved = useMemo(() => toForm(context.data?.latest?.values), [context.data]);
  const [form, setForm] = useState<BriefForm>(saved);
  const [confirm, setConfirm] = useState<Set<BriefField>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setForm(saved), [saved]); // a fresh AI draft or a save refills the form

  if (context.isLoading) return <p className="page">Loading the project context…</p>;
  const data = context.data;
  const editable = can("project.context");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await save.mutateAsync({
        fields: changedValues(form, saved),
        confirm: [...confirm],
        reason: data?.project_status === "active" ? "Edited in the setup wizard" : undefined,
      });
      setConfirm(new Set());
      if (result.activated) {
        notify("Context confirmed. The project is Active and analysis is on.", "success");
        navigate(`/w/${workspaceId}/p/${projectId}`);
      } else {
        notify("Saved.", "success");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save the context.");
    }
  };

  const fieldRow = (key: FormKey) => {
    const field = FIELD_OF[key];
    const status = statusOf(data, field);
    return (
      <div className="field" key={key}>
        <label htmlFor={`brief-${key}`}>
          {LABELS[key]} {REQUIRED.includes(key) && <span aria-hidden="true">*</span>}{" "}
          {status === "ai_drafted" && <Badge tone="ai">AI-drafted</Badge>}
          {status === "confirmed" && <Badge tone="approved">confirmed</Badge>}
        </label>
        <textarea
            id={`brief-${key}`}
            className="textarea"
            rows={key === "purpose" || key === "glossary" ? 4 : 2}
            required={REQUIRED.includes(key)}
            readOnly={!editable}
            value={form[key]}
            onChange={(event) => setForm({ ...form, [key]: event.target.value })}
          />
        {status === "ai_drafted" && editable && form[key] === saved[key] && (
          <label className="field-hint">
            <input
              type="checkbox"
              checked={confirm.has(field)}
              onChange={(event) => {
                const next = new Set(confirm);
                if (event.target.checked) next.add(field);
                else next.delete(field);
                setConfirm(next);
              }}
            />{" "}
            The AI draft is right — confirm it as it is
          </label>
        )}
      </div>
    );
  };

  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <div className="eyebrow">Project setup · step 2 of 2 · context</div>
      <h1 style={{ margin: "4px 0 8px" }}>Give the project its context</h1>
      <p className="muted">
        The AI reads this with every requirement, so it knows what the product is, who uses it and
        what your terms mean. Upload the initial SRS to have the brief drafted for you, write it
        yourself, or both.
      </p>
      {data && (
        <p role="status">
          <strong>
            {data.required_confirmed} of {data.required_total}
          </strong>{" "}
          required fields confirmed
          {data.missing_fields.length > 0 && <> · missing: {data.missing_fields.join(", ")}</>}
        </p>
      )}

      <section className="card" style={{ padding: 20, marginBottom: 24 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Initial SRS</h2>
        <DocumentProgressList documents={documents.data?.items ?? []} />
        {processing && (
          <p className="muted">Extracting… drafted fields appear below when it finishes.</p>
        )}
        {(can("doc.upload") || can("baseline.manage")) && (
          <Button onClick={() => setUploading(true)} style={{ marginTop: 12 }}>
            Upload initial SRS
          </Button>
        )}
      </section>

      <form onSubmit={submit} className="card" style={{ padding: 20 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Project brief</h2>
        {!editable && (
          <p className="muted">Only members who can edit the project context can change this.</p>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {REQUIRED.map(fieldRow)}
        <details>
          <summary>Optional: glossary, constraints, quality goals, regulations</summary>
          {OPTIONAL.map(fieldRow)}
        </details>
        {editable && (
          <div style={{ marginTop: 16 }}>
            <Button type="submit" variant="primary" loading={save.isPending}>
              Save and confirm
            </Button>
          </div>
        )}
      </form>
      <UploadDialog projectId={projectId} open={uploading} onClose={() => setUploading(false)} />
    </div>
  );
}
