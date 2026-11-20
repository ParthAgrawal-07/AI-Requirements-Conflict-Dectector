// The requirement composer's server calls (Pranshu — US-30, US-36; API by Bansil and Heet,
// contract in docs/contracts/composer-and-context.md).
//
// Query keys: ["composer-templates"] (static), ["drafts"] (the caller's private drafts),
// ["similar", projectId, text] (hints while typing).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { RequirementRead, RequirementState, UUID } from "../../api/types";
import type { Message } from "../channels/api";

export type TemplateKey =
  | "ubiquitous"
  | "event_driven"
  | "state_driven"
  | "unwanted_behaviour"
  | "optional_feature"
  | "free_text";
export type RequirementType = "functional" | "non_functional" | "constraint";
export type Priority = "must" | "should" | "could" | "wont";

export interface EarsSlot {
  key: string;
  label: string;
  placeholder: string;
}

export interface EarsTemplate {
  template: TemplateKey;
  chip: string;
  pattern: string; // "When {trigger}, the {system} shall {response}."
  slots: EarsSlot[];
  example: string;
}

export interface AcceptanceCriterion {
  given: string;
  when: string;
  then: string;
}

/** What the composer holds; a draft stores it as is (every field optional, FR-81). */
export interface ComposerFields {
  template: TemplateKey | null;
  slots: Record<string, string>;
  type: RequirementType | null;
  priority: Priority | null;
  stakeholder_group: string | null;
  owner_id: UUID | null; // null: me
  tags: string[];
  rationale: string | null;
  acceptance_criteria: AcceptanceCriterion[];
  channel_id: UUID | null; // null: the group's channel, else #general
}

export interface Draft {
  id: UUID;
  project_id: UUID;
  fields: ComposerFields;
  preview: string | null;
  updated_at: string;
}

export interface SimilarRequirement {
  requirement_id: UUID;
  label: string | null;
  state: RequirementState;
  preview: string;
  similarity: number;
}

export interface PostResult {
  message: Message;
  requirement: RequirementRead;
  analysis_run_id: UUID;
}

export const EMPTY_FIELDS: ComposerFields = {
  template: "event_driven",
  slots: {},
  type: "functional",
  priority: "must",
  stakeholder_group: null,
  owner_id: null,
  tags: [],
  rationale: null,
  acceptance_criteria: [],
  channel_id: null,
};

const filled = (c: AcceptanceCriterion) =>
  Boolean(c.given.trim() || c.when.trim() || c.then.trim());
const complete = (c: AcceptanceCriterion) =>
  Boolean(c.given.trim() && c.when.trim() && c.then.trim());

/** 1-based numbers of the criteria that are started but not finished: *Propose* waits for them. */
export function incompleteCriteria(fields: ComposerFields): number[] {
  return fields.acceptance_criteria.flatMap((c, i) => (filled(c) && !complete(c) ? [i + 1] : []));
}

/** What the server receives. Only the chosen template's slots go (the composer keeps the others
 *  locally so switching back restores them), and empty strings are dropped. A draft keeps
 *  half-written criteria (FR-81); a proposal is only sent once none is half-written. */
export function cleanFields(
  fields: ComposerFields,
  template: EarsTemplate | null,
  { draft }: { draft: boolean },
): ComposerFields {
  const active = new Set(template?.slots.map((slot) => slot.key) ?? []);
  const slots = Object.fromEntries(
    Object.entries(fields.slots).filter(([key, value]) => active.has(key) && value.trim() !== ""),
  );
  return {
    ...fields,
    slots,
    stakeholder_group: fields.stakeholder_group?.trim() || null,
    rationale: fields.rationale?.trim() || null,
    tags: fields.tags.map((tag) => tag.trim()).filter(Boolean),
    acceptance_criteria: fields.acceptance_criteria.filter(draft ? filled : complete),
  };
}

export function useTemplates() {
  return useQuery({
    queryKey: ["composer-templates"],
    queryFn: () => apiFetch<EarsTemplate[]>("/composer/templates"),
    staleTime: Infinity,
  });
}

export function useDrafts(projectId: string) {
  return useQuery({
    queryKey: ["drafts"],
    queryFn: () => apiFetch<Draft[]>("/me/drafts"),
    select: (drafts) => drafts.filter((draft) => draft.project_id === projectId),
  });
}

/** Create the draft on the first save, update it afterwards. ``fields`` is already cleaned
 *  (``cleanFields(…, { draft: true })``). */
export function useSaveDraft(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, fields }: { id: UUID | null; fields: ComposerFields }) =>
      id
        ? apiFetch<Draft>(`/me/drafts/${id}`, {
            method: "PATCH",
            json: { fields },
          })
        : apiFetch<Draft>("/me/drafts", {
            method: "POST",
            json: { project_id: projectId, fields },
          }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["drafts"] }),
  });
}

/** Similar requirements for the text being written (embedding only, nothing stored). */
export function useSimilar(projectId: string, text: string, enabled: boolean) {
  return useQuery({
    queryKey: ["similar", projectId, text],
    enabled: enabled && text.trim().length >= 12,
    queryFn: ({ signal }) =>
      apiFetch<{ hints: SimilarRequirement[] }>(`/projects/${projectId}/similar`, {
        method: "POST",
        json: { text, k: 3 },
        signal,
      }),
    staleTime: 60_000,
  });
}

/** ``fields`` is already cleaned (``cleanFields(…, { draft: false })``). */
export function usePropose(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      fields,
      draftId,
      supersedes,
      sourceSuggestionId,
    }: {
      fields: ComposerFields;
      draftId: UUID | null;
      supersedes?: UUID; // US-45: the member's own proposal this post replaces
      sourceSuggestionId?: UUID;
    }) =>
      apiFetch<PostResult>(`/projects/${projectId}/requirements`, {
        method: "POST",
        json: {
          fields,
          draft_id: draftId,
          supersedes: supersedes ?? null,
          source_suggestion_id: sourceSuggestionId ?? null,
        },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["requirements", projectId],
      });
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });
}
