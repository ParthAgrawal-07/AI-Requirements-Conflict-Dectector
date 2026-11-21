import { QueryClient } from "@tanstack/react-query";
import { fireEvent } from "@testing-library/react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyEvent } from "../src/app/socket";
import { ChangeEditor } from "../src/features/changes/ChangeEditor";
import { SuggestionPanel } from "../src/features/findings/SuggestionPanel";
import { Bell } from "../src/features/notifications/Bell";
import { Inbox } from "../src/features/notifications/Inbox";
import { ThresholdsTab } from "../src/features/members/ProjectSettings";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Developer", is_default: true },
  permissions: granted,
  protected_only: [],
});

const FINDING = {
  id: "f1",
  category: "Conflicting",
  requirements: [
    { id: "r12", label: "REQ-012", body: "Sessions shall time out after 30 minutes." },
    { id: "r31", label: "REQ-031", body: "Payment screens shall time out after 5 minutes." },
  ],
};

const READY = {
  id: "s1",
  finding_id: "f1",
  category: "Conflicting",
  status: "ready",
  label: "AI",
  instruction: null,
  error: null,
  my_outcome: null,
  preferences: [
    { user_id: "u-riya", full_name: "Riya", option_index: 1 },
    { user_id: "u-arjun", full_name: "Arjun", option_index: 1 },
  ],
  options: [
    { text: "Sessions shall time out after 5 minutes.", target: "REQ-012", target_requirement_id: "r12", trade_off: "Shorter web sessions.", confidence: 0.71, tbd_slots: [] },
    { text: "Sessions shall time out after 15 minutes.", target: "REQ-012", target_requirement_id: "r12", trade_off: "A compromise.", confidence: 0.82, tbd_slots: [] },
    { text: "Payment screens shall time out after [TBD — confirm].", target: "REQ-031", target_requirement_id: "r31", trade_off: "Someone decides.", confidence: 0.4, tbd_slots: ["payment timeout"] },
  ],
};

const panelRoute = { route: "/w/w1/p/p1/findings", path: "/w/:workspaceId/p/:projectId/findings" };

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search} {JSON.stringify(location.state)}</p>;
}

describe("SuggestionPanel (US-45)", () => {
  const api = (extra: Record<string, unknown> = {}) =>
    mockApi({
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "req.comment", "rcr.open"]),
      "GET /api/v1/findings/f1/suggestions": READY,
      "GET /api/v1/findings/f1": FINDING,
      ...extra,
    });

  it("shows three labelled options with trade-offs, confidence and both owners' preference", async () => {
    api();
    renderWithProviders(<SuggestionPanel findingId="f1" />, panelRoute);
    const panel = await screen.findByRole("region", { name: "Suggested solutions" });
    expect(within(panel).getByText("AI", { selector: ".badge-ai" })).toBeInTheDocument();
    expect(within(panel).getAllByRole("radio")).toHaveLength(3);
    expect(within(panel).getByText("Riya ✓ · Arjun ✓", { exact: false })).toBeInTheDocument();
    expect(within(panel).getByText("[TBD — confirm]").tagName).toBe("MARK");
    const diff = await screen.findByLabelText("Diff for option A");
    expect(diff.querySelector("del")).toHaveTextContent("30");
    expect(within(panel).getByText(/Accepting one does not mean it is correct/)).toBeInTheDocument();
  });

  it("accepting opens the change editor pre-filled, linked to the issue", async () => {
    const { calls } = api({
      "POST /api/v1/suggestions/s1/feedback": [201, {
        feedback: { id: "fb", action: "accepted", option_index: 1 },
        prefill: { kind: "change_request", requirement_id: "r12", proposed_body: READY.options[1].text,
                   source_suggestion_id: "s1", finding_id: "f1", issue_id: "i4", issue_number: 4, tbd_slots: [] },
        suggestion: null,
      }],
    });
    const { user } = renderWithProviders(
      <Routes>
        <Route path="/w/:workspaceId/p/:projectId/findings" element={<SuggestionPanel findingId="f1" />} />
        <Route path="*" element={<Where />} />
      </Routes>,
      { route: "/w/w1/p/p1/findings" },
    );
    const panel = await screen.findByRole("region", { name: "Suggested solutions" });
    await user.click(within(panel).getAllByRole("radio")[1]);
    await user.click(within(panel).getByRole("button", { name: /Accept B/ }));
    expect(await screen.findByTestId("where")).toHaveTextContent("/w/w1/p/p1/changes/new?requirement=r12&resolves=4");
    expect(screen.getByTestId("where")).toHaveTextContent('"source_suggestion_id":"s1"');
    expect(JSON.parse(String(calls.find((c) => c.method === "POST")?.body))).toEqual({
      action: "accepted", option_index: 1, final_text: null, reason: null,
    });
  });

  it("records a structured rejection, a deferral and a preference", async () => {
    const { calls } = api({
      "POST /api/v1/suggestions/s1/feedback": [201, { feedback: { id: "fb", action: "x", option_index: 0 }, prefill: null, suggestion: null }],
    });
    const { user } = renderWithProviders(<SuggestionPanel findingId="f1" />, panelRoute);
    const panel = await screen.findByRole("region", { name: "Suggested solutions" });
    await user.click(within(panel).getByRole("button", { name: "changes the intended meaning" }));
    await user.click(within(panel).getByRole("button", { name: /Defer/ }));
    await user.click(within(panel).getByRole("button", { name: /Mark A as my preference/ }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(3));
    const actions = calls.filter((c) => c.method === "POST").map((c) => JSON.parse(String(c.body)));
    expect(actions.map((a) => [a.action, a.option_index])).toEqual([
      ["rejected_meaning", 0],
      ["deferred", null],
      ["prefer", 0],
    ]);
  });

  it("says when suggestions are still being generated", async () => {
    api({ "GET /api/v1/findings/f1/suggestions": { ...READY, status: "pending", options: [] } });
    renderWithProviders(<SuggestionPanel findingId="f1" />, panelRoute);
    expect(await screen.findByText("Generating suggestions…")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("regenerates with an instruction", async () => {
    const { calls } = api({
      "POST /api/v1/findings/f1/suggestions/regenerate": [202, { ...READY, id: "s2", status: "pending", options: [], instruction: "keep 30 minutes" }],
    });
    const { user } = renderWithProviders(<SuggestionPanel findingId="f1" />, panelRoute);
    await user.type(await screen.findByLabelText(/Regenerate with instruction/), "keep 30 minutes");
    await user.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(await screen.findByText("Generating suggestions…")).toBeInTheDocument();
    const post = calls.find((c) => c.path.endsWith("/regenerate"));
    expect(JSON.parse(String(post?.body))).toEqual({ instruction: "keep 30 minutes" });
  });

  it("refreshes when the suggestion is ready", () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    applyEvent(queryClient, { type: "suggestion.ready", workspace_id: "w1", project_id: "p1", channel_id: null, entity_id: "s1", at: "", data: { finding_id: "f1" } });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["suggestion", "f1"] });
  });
});

describe("Change editor from an accepted suggestion (US-45, US-33)", () => {
  it("opens pre-filled, links the suggestion and refuses unfilled placeholders", async () => {
    const prefill = { kind: "change_request", requirement_id: "r31", proposed_body: "Payment screens shall time out after [TBD — confirm].",
                      source_suggestion_id: "s1", finding_id: "f1", issue_id: "i4", issue_number: 4, tbd_slots: ["payment timeout"] };  // prettier-ignore
    const { calls } = mockApi({
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "rcr.open"]),
      "GET /api/v1/requirements/r31": { requirement_id: "r31", project_id: "p1", source_req_id: "REQ-031", body: "Payment screens shall time out after 5 minutes.", current_version: 1, state: "Approved", owner_id: null },
      "GET /api/v1/lint/catalogue": { version: 2, entries: [] },
      "GET /api/v1/projects/p1/issues": { items: [], total: 0, limit: 50, offset: 0 },
      "POST /api/v1/requirements/r31/change-requests": [201, { id: "cr9", number: 9 }],
    });
    const { user } = renderWithProviders(
      <Routes>
        <Route path="/start" element={<Navigate to="/w/w1/p/p1/changes/new?requirement=r31&resolves=4" state={{ prefill }} />} />
        <Route path="/w/:workspaceId/p/:projectId/changes/new" element={<ChangeEditor />} />
        <Route path="*" element={<Where />} />
      </Routes>,
      { route: "/start" },
    );
    const form = await screen.findByRole("form", { name: /Propose a change to REQ-031/ });
    const proposed = within(form).getByLabelText("Proposed text");
    expect(proposed).toHaveValue(prefill.proposed_body);
    expect(within(form).getByText(/Suggested by AI, accepted by you/)).toBeInTheDocument();
    expect(within(form).getByRole("alert")).toHaveTextContent("Replace every [TBD — confirm]");
    expect(within(form).getByRole("button", { name: "Open change request" })).toBeDisabled();

    await user.clear(proposed);
    await user.type(proposed, "Payment screens shall time out after 10 minutes.");
    expect(within(form).queryByRole("alert")).not.toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Open change request" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.method === "POST")?.body));
    expect(body).toMatchObject({ source_suggestion_id: "s1", resolves: [4] });
  });
});

describe("Inbox and bell (US-38)", () => {
  const COUNTS = { review: 1, assigned: 1, mentioned: 0, watching: 0, results: 0, join_requests: 0, total: 2 };
  const ROWS = [
    { id: "n1", kind: "review_requested", group: "review", workspace_id: "w1", project_id: "p1", subject_type: "change_request", subject_id: "cr1", actor_id: "u", payload: { title: "Review requested: RCR-3 on REQ-014", key: "RCR-3", url: "/w/w1/p/p1/changes/cr1" }, read: false, updated_at: "2026-12-20T10:00:00Z" },
    { id: "n2", kind: "assigned", group: "assigned", workspace_id: "w1", project_id: "p1", subject_type: "issue", subject_id: "i4", actor_id: null, payload: { title: "ISS-4 was assigned to you", key: "ISS-4", url: "/w/w1/p/p1/issues/i4" }, read: false, updated_at: "2026-12-20T09:00:00Z" },
  ];

  it("shows the unread count on the bell", async () => {
    mockApi({ "GET /api/v1/notifications/counts": COUNTS });
    renderWithProviders(<Bell />);
    expect(await screen.findByRole("link", { name: "Inbox, 2 unread" })).toHaveAttribute("href", "/inbox");
  });

  it("groups by reason, links each item to its subject and marks it done", async () => {
    const { calls } = mockApi({
      "GET /api/v1/notifications/counts": COUNTS,
      "GET /api/v1/notifications?unread=true": ROWS,
      "GET /api/v1/notifications?group=review&unread=true": [ROWS[0]],
      "POST /api/v1/notifications/read": { marked: 1 },
    });
    const { user } = renderWithProviders(<Inbox />);
    const link = await screen.findByRole("link", { name: "Review requested: RCR-3 on REQ-014" });
    expect(link).toHaveAttribute("href", "/w/w1/p/p1/changes/cr1");
    await user.click(screen.getByRole("button", { name: /Review requested/ }));
    await waitFor(() => expect(screen.queryByText("ISS-4 was assigned to you")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Mark done" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toBe(JSON.stringify({ ids: ["n1"] }));
    await user.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST").map((c) => c.body)).toContain(JSON.stringify({ all: true })));
  });

  it("a notification event refreshes the inbox and the bell", () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    applyEvent(queryClient, { type: "notification.created", workspace_id: "w1", project_id: "p1", channel_id: null, entity_id: "n1", at: "", data: { recipient_id: "me" } });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["notifications"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["notification-counts"] });
  });
});

describe("Thresholds (US-06)", () => {
  it("previews a candidate threshold, then saves and re-analyses", async () => {
    const preview = (similarity: number) => ({
      similarity: { threshold: similarity, current: 0.75, pairs_above: similarity < 0.75 ? 9 : 4, pairs_compared: 21, truncated: false,
                    above: [{ a_label: "REQ-1", b_label: "REQ-2", similarity: 0.8, finding: "Conflicting", found_by: "ai" }], below: [] },
      confidence: { threshold: 0.5, current: 0.5, confident: 3, low_confidence: 1 },
    });  // prettier-ignore
    const { calls } = mockApi({
      "GET /api/v1/projects/p1": { id: "p1", similarity_threshold: 0.75, confidence_threshold: 0.5 },
      "GET /api/v1/projects/p1/thresholds/preview?similarity=0.75&confidence=0.5": preview(0.75),
      "GET /api/v1/projects/p1/thresholds/preview?similarity=0.7&confidence=0.5": preview(0.7),
      "PATCH /api/v1/projects/p1": { id: "p1" },
      "POST /api/v1/projects/p1/reanalyse": [202, { queued: 2 }],
    });
    const { user } = renderWithProviders(<ThresholdsTab projectId="p1" />);
    expect(await screen.findByText(/pairs would be compared/)).toHaveTextContent("4 of 21");
    expect(screen.getByText(/REQ-1 · REQ-2/).closest("li")).toHaveTextContent("Conflicting (AI)");
    fireEvent.change(screen.getByLabelText(/Similarity threshold/), { target: { value: "0.7" } });
    await waitFor(() => expect(screen.getByText(/pairs would be compared/)).toHaveTextContent("9 of 21"), { timeout: 3000 });
    await user.click(screen.getByRole("button", { name: "Save thresholds" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.method === "PATCH")?.body))).toEqual({ similarity_threshold: 0.7, confidence_threshold: 0.5 });
    await user.click(screen.getByRole("button", { name: "Re-analyse the project" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/reanalyse"))).toBe(true));
  });
});
