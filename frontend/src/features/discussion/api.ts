// Discussion, votes, watch and links (Madhav — US-53; API in backend/app/api/social.py).
// Keys: ["social", requirementId] the drawer summary, ["comments", requirementId] the thread,
// ["votes", subjectType, id], ["watch", subjectType, id]. A `requirement.activity` event
// invalidates the requirement's keys (app/socket.ts).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type Stance = "support" | "oppose";
export type LinkKind = "depends_on" | "refines" | "related_to";
export type WatchSubject = "requirements" | "issues" | "change-requests";
export type VoteSubject = "requirements" | "change-requests";

export const LINK_WORDS: Record<LinkKind, string> = {
  depends_on: "depends on",
  refines: "refines",
  related_to: "is related to",
};

export interface Comment {
  id: UUID;
  author_id: UUID | null;
  author_name: string | null;
  body: string;
  created_at: string;
  edited_at: string | null;
}

export interface Vote {
  user_id: UUID;
  user_name: string | null;
  stance: Stance;
  reason: string | null;
}

export interface Tally {
  support: number;
  oppose: number;
  mine: Stance | null;
  votes: Vote[];
  decides: false;
}

export interface Watch {
  watching: boolean;
  watchers: number;
}

export interface Link {
  id: UUID;
  source_id: UUID;
  source_label: string | null;
  target_id: UUID;
  target_label: string | null;
  kind: LinkKind;
  direction: "outgoing" | "incoming";
  note: string | null;
  created_by: UUID | null;
  created_by_name: string | null;
  created_at: string;
  found_by: "person";
}

export interface Social {
  requirement_id: UUID;
  comments: number;
  votes: Tally;
  watching: boolean;
  links: Link[];
}

export function useSocial(requirementId: string) {
  return useQuery({
    queryKey: ["social", requirementId],
    queryFn: () => apiFetch<Social>(`/requirements/${requirementId}/social`),
  });
}

export function useComments(requirementId: string, enabled = true) {
  return useQuery({
    queryKey: ["comments", requirementId],
    enabled,
    queryFn: () => apiFetch<Comment[]>(`/requirements/${requirementId}/comments`),
  });
}

export function useAddComment(requirementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { body: string; mentions?: UUID[] }) =>
      apiFetch<Comment>(`/requirements/${requirementId}/comments`, { method: "POST", json: input }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["comments", requirementId] });
      void queryClient.invalidateQueries({ queryKey: ["social", requirementId] });
    },
  });
}

export function useVotes(subject: VoteSubject, id: string) {
  return useQuery({
    queryKey: ["votes", subject, id],
    queryFn: () => apiFetch<Tally>(`/${subject}/${id}/votes`),
  });
}

export function useVote(subject: VoteSubject, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { stance: Stance; reason?: string } | null) =>
      input
        ? apiFetch<Tally>(`/${subject}/${id}/vote`, { method: "PUT", json: input })
        : apiFetch<Tally>(`/${subject}/${id}/vote`, { method: "DELETE" }),
    onSuccess: (tally) => {
      queryClient.setQueryData(["votes", subject, id], tally);
      if (subject === "requirements") void queryClient.invalidateQueries({ queryKey: ["social", id] });
    },
  });
}

export function useWatch(subject: WatchSubject, id: string) {
  return useQuery({
    queryKey: ["watch", subject, id],
    queryFn: () => apiFetch<Watch>(`/${subject}/${id}/watch`),
  });
}

export function useSetWatch(subject: WatchSubject, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (on: boolean) => apiFetch<Watch>(`/${subject}/${id}/watch`, { method: on ? "PUT" : "DELETE" }),
    onSuccess: (watch) => {
      queryClient.setQueryData(["watch", subject, id], watch);
      if (subject === "requirements") void queryClient.invalidateQueries({ queryKey: ["social", id] });
    },
  });
}

export function useAddLink(requirementId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { target_id: UUID; kind: LinkKind; note?: string }) =>
      apiFetch<Link>(`/requirements/${requirementId}/links`, { method: "POST", json: input }),
    onSuccess: (link) => {
      void queryClient.invalidateQueries({ queryKey: ["social", requirementId] });
      void queryClient.invalidateQueries({ queryKey: ["social", link.target_id] });
      void queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
    },
  });
}

export function useRemoveLink(requirementId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (link: Link) =>
      apiFetch<void>(`/requirements/${requirementId}/links/${link.id}`, { method: "DELETE" }),
    onSuccess: (_, link) => {
      void queryClient.invalidateQueries({ queryKey: ["social", link.source_id] });
      void queryClient.invalidateQueries({ queryKey: ["social", link.target_id] });
      void queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
    },
  });
}
