// Inbox and notifications (Abhijeet — US-38 UI; API by Madhav: GET /notifications,
// GET /notifications/counts, POST /notifications/read). Keys: ["notifications", group, unread]
// and ["notification-counts"]; a notification.created event (sent to its recipient only)
// refreshes both (app/socket.ts).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type InboxGroup = "review" | "assigned" | "mentioned" | "watching" | "results" | "join_requests";

export const GROUPS: { id: InboxGroup; label: string }[] = [
  { id: "review", label: "Review requested" },
  { id: "assigned", label: "Assigned" },
  { id: "mentioned", label: "Mentioned" },
  { id: "watching", label: "Watching" },
  { id: "results", label: "Results on my requirements" },
  { id: "join_requests", label: "Join requests" },
];

export interface Notification {
  id: UUID;
  kind: string;
  group: InboxGroup;
  workspace_id: UUID;
  project_id: UUID | null;
  subject_type: string;
  subject_id: UUID;
  actor_id: UUID | null;
  payload: { title: string; key: string; url: string };
  read: boolean;
  updated_at: string;
}

export type Counts = Record<InboxGroup, number> & { total: number };

export function useNotifications(group: InboxGroup | null, unread: boolean) {
  return useQuery({
    queryKey: ["notifications", group, unread],
    queryFn: () =>
      apiFetch<Notification[]>("/notifications", { query: { group: group ?? undefined, unread: unread || undefined } }),
  });
}

export function useNotificationCounts(enabled = true) {
  return useQuery({
    queryKey: ["notification-counts"],
    enabled,
    queryFn: () => apiFetch<Counts>("/notifications/counts"),
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: UUID[] | "all") =>
      apiFetch<{ marked: number }>("/notifications/read", {
        method: "POST",
        json: ids === "all" ? { all: true } : { ids },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notification-counts"] });
    },
  });
}
