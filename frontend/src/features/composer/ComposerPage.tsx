import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useChannels, useMembers } from "../channels/api";
import {
  EMPTY_FIELDS,
  usePropose,
  useSaveDraft,
  useSimilar,
  useTemplates,
  useDrafts,
  type AcceptanceCriterion,
  type ComposerFields,
  type Priority,
  type RequirementType,
} from "./api";
import { missingSlots, renderStatement } from "./ears";
import { EarsTemplatePicker } from "./EarsTemplatePicker";
import { PreviewPane } from "./PreviewPane";
import { SlotFields } from "./SlotFields";

export const AUTOSAVE_MS = 5_000; // interface design §5.2
const SIMILAR_DEBOUNCE_MS = 800;
const TYPES: { value: RequirementType; label: string }[] = [
  { value: "functional", label: "Functional" },
  { value: "non_functional", label: "Non-functional" },
  { value: "constraint", label: "Constraint" },
];
const PRIORITIES: { value: Priority; label: string }[] = [
  { value: "must", label: "Must" },
  { value: "should", label: "Should" },
  { value: "could", label: "Could" },
  { value: "wont", label: "Won't" },
];

type SaveState = "clean" | "dirty" | "saving" | "saved" | "error";

/** The requirement composer (US-30, interface design §5): an EARS template with labelled slots,
 *  a live preview, the requirement's fields and owner (US-36), similar requirements as you type,
 *  a private draft saved every 5 s, and *Propose*, which posts the card and starts live analysis.
 *  Members who may not propose (viewers, compliance reviewers) get no form at all. */
export function ComposerPage() {
  const { workspaceId = "", projectId = "" } = useParams();
  const { user } = useAuth();
  const { can, isLoading: permissionsLoading } = usePermissions({ projectId });
  const navigate = useNavigate();
  const notify = useToast();
  const templates = useTemplates();
  const members = useMembers(workspaceId);
  const channels = useChannels(projectId);
  const drafts = useDrafts(projectId);
  const saveDraft = useSaveDraft(projectId);
  const propose = usePropose(projectId);

  const [fields, setFields] = useState<ComposerFields>(EMPTY_FIELDS);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("clean");
  const [similarText, setSimilarText] = useState("");
  const [tagText, setTagText] = useState("");

  const me = members.data?.find((member) => member.user.id === user?.id);
  const template = templates.data?.find((t) => t.template === fields.template) ?? null;
  const statement = template ? renderStatement(template, fields.slots) : null;
  const missing = template ? missingSlots(template, fields.slots) : ["a template"];
  const similar = useSimilar(projectId, similarText, can("req.propose"));

  const update = useCallback((change: Partial<ComposerFields>) => {
    setFields((current) => ({ ...current, ...change }));
    setSaveState("dirty");
  }, []);

  // The similar panel follows what is being written, 800 ms after typing stops.
  useEffect(() => {
    const text = statement ?? Object.values(fields.slots).join(" ");
    const timer = setTimeout(() => setSimilarText(text.trim()), SIMILAR_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [statement, fields.slots]);

  // Autosave every 5 s while there are unsaved changes (a private draft, FR-81).
  // Refs, not dependencies: the interval must survive re-renders (typing re-renders every key).
  const latest = useRef({ fields, draftId, saveState, save: saveDraft.mutate });
  latest.current = { fields, draftId, saveState, save: saveDraft.mutate };
  useEffect(() => {
    const timer = setInterval(() => {
      const { fields: current, draftId: id, saveState: state, save } = latest.current;
      if (state !== "dirty") return;
      setSaveState("saving");
      save(
        { id, fields: current },
        {
          onSuccess: (draft) => {
            setDraftId(draft.id);
            setSaveState((now) => (now === "saving" ? "saved" : now));
          },
          onError: () => setSaveState("error"),
        },
      );
    }, AUTOSAVE_MS);
    return () => clearInterval(timer);
  }, []);

  const ready = Boolean(statement && fields.type && fields.priority);
  const submit = useCallback(() => {
    if (!ready || propose.isPending) return;
    propose.mutate(
      { fields, draftId },
      {
        onSuccess: (result) => {
          const label = result.requirement.source_req_id ?? "The requirement";
          notify(`${label} proposed — live analysis started`, "success");
          navigate(`/w/${workspaceId}/p/${projectId}/channels/${result.message.channel_id}`);
        },
        onError: (error) =>
          notify(error instanceof ApiError ? error.message : "Could not propose it", "error"),
      },
    );
  }, [ready, propose, fields, draftId, notify, navigate, workspaceId, projectId]);

  const resumable = useMemo(
    () => (drafts.data ?? []).filter((d) => d.id !== draftId),
    [drafts.data, draftId],
  );

  if (permissionsLoading) return <p className="page">Loading…</p>;
  if (!can("req.propose")) {
    return (
      <div className="page">
        <h1>New requirement</h1>
        <p className="muted">
          Your role cannot propose requirements in this project. You can still read the map, the
          requirements and their findings.
        </p>
      </div>
    );
  }

  return (
    <form
      className="page composer-page"
      aria-labelledby="composer-title"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          submit();
        }
      }}
    >
      <header className="composer-header">
        <h1 id="composer-title">New requirement</h1>
        <span className="muted small" role="status">
          {saveState === "saving" && "Saving draft…"}
          {saveState === "saved" && "Draft saved ✓"}
          {saveState === "error" && "Draft not saved — check your connection"}
          {saveState === "dirty" && "Unsaved changes"}
        </span>
      </header>

      {resumable.length > 0 && saveState === "clean" && (
        <p className="banner">
          You have {resumable.length} saved {resumable.length === 1 ? "draft" : "drafts"}.{" "}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const draft = resumable[0];
              setFields({
                ...EMPTY_FIELDS,
                ...draft.fields,
                slots: draft.fields.slots ?? {},
              });
              setDraftId(draft.id);
              setSaveState("saved");
            }}
          >
            Resume the latest
          </Button>
        </p>
      )}

      <div className="composer-grid">
        <div className="composer-main">
          {templates.data && (
            <EarsTemplatePicker
              templates={templates.data}
              value={fields.template}
              onChange={(next) => update({ template: next })}
            />
          )}
          {template && (
            <SlotFields
              template={template}
              slots={fields.slots}
              onChange={(key, value) => update({ slots: { ...fields.slots, [key]: value } })}
            />
          )}

          <div className="field-row">
            <label>
              Type
              <select
                value={fields.type ?? ""}
                onChange={(e) => update({ type: e.target.value as RequirementType })}
              >
                {TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Priority
              <select
                value={fields.priority ?? ""}
                onChange={(e) => update({ priority: e.target.value as Priority })}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Group
              <input
                value={fields.stakeholder_group ?? ""}
                placeholder={me?.stakeholder_group ?? "Your group"}
                maxLength={120}
                onChange={(e) => update({ stakeholder_group: e.target.value })}
              />
            </label>
            <label>
              Owner
              <select
                value={fields.owner_id ?? ""}
                onChange={(e) => update({ owner_id: e.target.value || null })}
              >
                <option value="">Me</option>
                {(members.data ?? [])
                  .filter((m) => m.user.id !== user?.id)
                  .map((m) => (
                    <option key={m.user.id} value={m.user.id}>
                      {m.user.full_name}
                    </option>
                  ))}
              </select>
            </label>
          </div>

          <label className="field">
            Tags <span className="muted small">(comma-separated)</span>
            <input
              value={tagText}
              onChange={(e) => {
                setTagText(e.target.value);
                update({ tags: e.target.value.split(",").slice(0, 10) });
              }}
            />
          </label>
          <label className="field">
            Rationale
            <textarea
              rows={2}
              maxLength={2000}
              value={fields.rationale ?? ""}
              onChange={(e) => update({ rationale: e.target.value })}
            />
          </label>

          <fieldset className="criteria">
            <legend>Acceptance criteria</legend>
            {fields.acceptance_criteria.map((criterion, index) => (
              <CriterionRow
                key={index}
                index={index}
                criterion={criterion}
                onChange={(next) =>
                  update({
                    acceptance_criteria: fields.acceptance_criteria.map((c, i) =>
                      i === index ? next : c,
                    ),
                  })
                }
                onRemove={() =>
                  update({
                    acceptance_criteria: fields.acceptance_criteria.filter((_, i) => i !== index),
                  })
                }
              />
            ))}
            {fields.acceptance_criteria.length < 10 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  update({
                    acceptance_criteria: [
                      ...fields.acceptance_criteria,
                      { given: "", when: "", then: "" },
                    ],
                  })
                }
              >
                + Criterion
              </Button>
            )}
          </fieldset>

          <label className="field">
            Post in
            <select
              value={fields.channel_id ?? ""}
              onChange={(e) => update({ channel_id: e.target.value || null })}
            >
              <option value="">The group&apos;s channel, else #general</option>
              {(channels.data ?? [])
                .filter((c) => !c.archived_at)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    #{c.name}
                  </option>
                ))}
            </select>
          </label>
        </div>

        <PreviewPane
          statement={statement}
          missing={missing}
          similar={similar.data?.hints ?? []}
          similarLoading={similar.isFetching}
        />
      </div>

      <footer className="composer-footer">
        <Button
          onClick={() => {
            setSaveState("saving");
            saveDraft.mutate(
              { id: draftId, fields },
              {
                onSuccess: (draft) => {
                  setDraftId(draft.id);
                  setSaveState("saved");
                },
                onError: () => setSaveState("error"),
              },
            );
          }}
        >
          Save draft
        </Button>
        <Button type="submit" variant="accent" disabled={!ready} loading={propose.isPending}>
          Propose requirement <kbd>Ctrl ⏎</kbd>
        </Button>
      </footer>
    </form>
  );
}

function CriterionRow({
  index,
  criterion,
  onChange,
  onRemove,
}: {
  index: number;
  criterion: AcceptanceCriterion;
  onChange: (next: AcceptanceCriterion) => void;
  onRemove: () => void;
}) {
  return (
    <div className="criterion" role="group" aria-label={`Criterion ${index + 1}`}>
      {(["given", "when", "then"] as const).map((part) => (
        <label key={part}>
          {part[0].toUpperCase() + part.slice(1)}
          <input
            value={criterion[part]}
            maxLength={500}
            onChange={(e) => onChange({ ...criterion, [part]: e.target.value })}
          />
        </label>
      ))}
      <Button
        size="sm"
        variant="ghost"
        onClick={onRemove}
        aria-label={`Remove criterion ${index + 1}`}
      >
        Remove
      </Button>
    </div>
  );
}
