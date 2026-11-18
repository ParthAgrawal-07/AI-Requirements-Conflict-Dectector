// A live analysis run and its findings (Pranshu — US-31; API by Keval: GET /analysis-runs/{id}).
// Key ["analysis-run", runId, version]: the card's message is rewritten when the run moves on
// (waiting for budget → done, a question added), and its edit time is the version.

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";
import type { Finding } from "../findings/api";

/** A finding of the run, with its clarification question once generated (US-09). */
export type RunFinding = Finding;

export type RunStatus = "queued" | "running" | "waiting_budget" | "done" | "failed";

export interface AnalysisRun {
  id: UUID;
  project_id: UUID;
  scope: "document" | "requirement" | "change_request";
  subject_id: UUID;
  status: RunStatus;
  pairs_total: number;
  pairs_failed: number;
  checks_total: number;
  checks_failed: number;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  findings: RunFinding[];
}

export function useAnalysisRun(runId: string | null, version: string | null) {
  return useQuery({
    queryKey: ["analysis-run", runId, version],
    enabled: Boolean(runId),
    queryFn: () => apiFetch<AnalysisRun>(`/analysis-runs/${runId}`),
  });
}
