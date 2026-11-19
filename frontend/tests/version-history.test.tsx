import { afterEach, describe, expect, it, vi } from "vitest";
import { wordDiff } from "../src/components/WordDiff";
import { VersionHistory } from "../src/features/requirements/VersionHistory";
import { mockApi, renderWithProviders, screen, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

describe("wordDiff", () => {
  it("marks the words that changed and keeps the rest verbatim", () => {
    expect(
      wordDiff(
        "Sessions shall expire after 30 minutes of inactivity.",
        "Sessions shall expire after 15 minutes of inactivity.",
      ),
    ).toEqual([
      { kind: "same", text: "Sessions shall expire after " },
      { kind: "removed", text: "30 " },
      { kind: "added", text: "15 " },
      { kind: "same", text: "minutes of inactivity." },
    ]);
  });

  it("handles added and removed tails", () => {
    expect(wordDiff("Log in.", "Log in. Then out.")).toEqual([
      { kind: "same", text: "Log in. " },
      { kind: "added", text: "Then out." },
    ]);
    expect(wordDiff("a b c", "")).toEqual([{ kind: "removed", text: "a b c" }]);
  });
});

describe("VersionHistory", () => {
  it("lists versions newest first, with who, the change request and the diff", async () => {
    mockApi({
      "GET /api/v1/requirements/r14/versions": [
        {
          version_no: 2,
          body: "Sessions shall expire after 15 minutes of inactivity.",
          changed_by: { id: "u-dev", full_name: "Dev" },
          changed_at: "2026-12-05T10:00:00Z",
          change_request: { id: "cr1", key: "RCR-1" },
        },
        {
          version_no: 1,
          body: "Sessions shall expire after 30 minutes of inactivity.",
          changed_by: null,
          changed_at: "2026-11-01T10:00:00Z",
          change_request: null,
        },
      ],
    });
    renderWithProviders(<VersionHistory requirementId="r14" />, {
      route: "/w/w1/p/p1/requirements",
      path: "/w/:workspaceId/p/:projectId/requirements",
    });

    const list = await screen.findByRole("list", { name: "Versions" });
    const [newest, oldest] = within(list).getAllByRole("listitem");
    expect(within(newest).getByText("v2")).toBeInTheDocument();
    expect(within(newest).getByText(/Dev/)).toBeInTheDocument();
    expect(within(newest).getByRole("link", { name: "RCR-1" })).toHaveAttribute("href", "/w/w1/p/p1/changes/cr1");
    const diff = within(newest).getByLabelText("Changes from v1");
    expect(diff.querySelector("del")).toHaveTextContent("removed: 30");
    expect(diff.querySelector("ins")).toHaveTextContent("added: 15");
    expect(within(oldest).getByText(/From the document/)).toBeInTheDocument();
  });
});
