import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useChannels, useMembers } from "../channels/api";
import type { Prefill } from "../findings/suggestions";
import {
  cleanFields,
  EMPTY_FIELDS,
  incompleteCriteria,
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
import { AuthoringPanel } from "./AuthoringPanel";
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
  const { projectId = "" } = useParams();
  // A new project is a new composer: its fields and draft must not carry over (or autosave the
  // previous project's draft through this project's hooks).
  return <Composer key={projectId} />;
}

function Composer() {
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

  // US-45: accepting a suggestion for one's own proposal opens a post that supersedes it.
  const prefill = (useLocation().state as { prefill?: Prefill } | null)?.prefill ?? null;
  const [fields, setFields] = useState<ComposerFields>(
    prefill ? { ...EMPTY_FIELDS, template: "free_text", slots: { statement: prefill.proposed_body } } : EMPTY_FIELDS,
  );
  const [draftId, setDraftId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("clean");
  const [similarText, setSimilarText] = useState("");
  const [tagText, setTagText] = useState("");

  const me = members.data?.find((member) => member.user.id === user?.id);
  const template = templates.data?.find((t) => t.template === fields.template) ?? null;
  const statement = template ? renderStatement(template, fields.slots) : null;
  const missing = template ? missingSlots(template, fields.slots) : ["a template"];
  const similar = useSimilar(projectId, similarText, can("req.propose"));

  // Every edit bumps the revision; a save is "saved" only if nothing changed while it ran.
  const revision = useRef(0);
  const update = useCallback((change: Partial<ComposerFields>) => {
    setFields((current) => ({ ...current, ...change }));
    revision.current += 1;
    setSaveState("dirty");
  }, []);

  // The similar panel follows what is being written, 800 ms after typing stops.
  useEffect(() => {
    const text = statement ?? Object.values(fields.slots).join(" ");
    const timer = setTimeout(() => setSimilarText(text.trim()), SIMILAR_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [statement, fields.slots]);

  // One save at a time, for autosave and *Save draft* alike: two first saves would create two
  // drafts, and an older PATCH finishing last would overwrite newer fields. Refs, not
  // dependencies: the autosave interval must survive re-renders (typing re-renders every key).
  const latest = useRef({
    fields,
    template,
    saveState,
    save: saveDraft.mutate,
  });
  latest.current = { fields, template, saveState, save: saveDraft.mutate };
  const draftRef = useRef<string | null>(null);
  const saving = useRef(false);
  const saveNow = useCallback(() => {
    if (saving.current) return; // the running save leaves newer edits "dirty" for the next tick
    const { fields: current, template: chosen, save } = latest.current;
    const snapshot = revision.current;
    saving.current = true;
    setSaveState("saving");
    save(
      {
        id: draftRef.current,
        fields: cleanFields(current, chosen, { draft: true }),
      },
      {
        onSuccess: (draft) => {
          draftRef.current = draft.id;
          setDraftId(draft.id);
          setSaveState(revision.current === snapshot ? "saved" : "dirty");
        },
        onError: () => setSaveState("error"),
        onSettled: () => {
          saving.current = false;
        },
      },
    );
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      if (latest.current.saveState === "dirty") saveNow();
    }, AUTOSAVE_MS);
    return () => clearInterval(timer);
  }, [saveNow]);

  const unfinished = incompleteCriteria(fields);
  const ready = Boolean(statement && fields.type && fields.priority && unfinished.length === 0);
  const submit = useCallback(() => {
    if (!ready || propose.isPending) return;
    propose.mutate(
      {
        fields: cleanFields(fields, template, { draft: false }),
        draftId,
        supersedes: prefill?.requirement_id,
        sourceSuggestionId: prefill?.source_suggestion_id,
      },
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
  }, [ready, propose, fields, template, draftId, prefill, notify, navigate, workspaceId, projectId]);

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
              const tags = draft.fields.tags ?? [];
              setFields({
                ...EMPTY_FIELDS,
                ...draft.fields,
                slots: draft.fields.slots ?? {},
                tags,
              });
              setTagText(tags.join(", "));
              draftRef.current = draft.id;
              setDraftId(draft.id);
              revision.current += 1;
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
        >
          {can("req.propose") && (
            <AuthoringPanel
              projectId={projectId}
              text={statement ?? Object.values(fields.slots).join(" ")}
              onUseWording={(proposed) =>
                update({ template: "free_text", slots: { statement: proposed } })
              }
            />
          )}
        </PreviewPane>
      </div>

      <footer className="composer-footer">
        {unfinished.length > 0 && (
          <p className="muted small" role="status">
            Finish or remove criterion {unfinished.join(", ")} to propose.
          </p>
        )}
        <Button onClick={saveNow}>Save draft</Button>
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
