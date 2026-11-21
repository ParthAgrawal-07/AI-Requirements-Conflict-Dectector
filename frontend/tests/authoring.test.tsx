import { afterEach, describe, expect, it, vi } from "vitest";
import { lint, scoreOf, segments, type LintCatalogue } from "../src/features/composer/authoring";
import { AuthoringPanel } from "../src/features/composer/AuthoringPanel";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

// The shape of backend/app/lint/catalogue.json (a few of its entries, verbatim patterns).
const CATALOGUE: LintCatalogue = {
  version: 2,
  entries: [
    { id: "vague.speed", category: "vague", pattern: "\\b(fast|quick|quickly)\\b", message: "Speed word without a number.", hint: "Say how fast.", severity: "warning" },
    { id: "tbd.placeholder", category: "tbd", pattern: "\\b(TBD|TBC)\\b", message: "Placeholder left in the requirement.", hint: "Fill it in.", severity: "error" },
    { id: "measure.missing", category: "measure", pattern: "\\b(within|timeout)\\b(?![^.;]*\\d)", message: "A measure without a number.", hint: "Give the value.", severity: "warning" },
    { id: "compound.multiple_shall", category: "compound", pattern: "\\b(shall)\\b(?=[\\s\\S]*\\bshall\\b)", message: "More than one shall.", hint: "Split it.", severity: "warning" },
  ],
};

describe("lint in the browser (US-51, NFR-34)", () => {
  it("finds the same issues as the server, in reading order, with offsets", () => {
    const text = "The page shall load quickly and shall respond within the timeout. TBD";
    const result = lint(text, CATALOGUE);
    expect(result.issues.map((issue) => issue.ruleId)).toEqual([
      "compound.multiple_shall",
      "vague.speed",
      "measure.missing",
      "measure.missing",
      "tbd.placeholder",
    ]);
    for (const issue of result.issues) expect(text.slice(issue.start, issue.end)).toBe(issue.match);
    expect(result.score).toBe(100 - 4 * 10 - 25);
    expect(result.quality).toBe("poor");
  });

  it("uses the server's weights and bands", () => {
    expect(scoreOf([])).toEqual({ score: 100, quality: "good" });
    const two = lint("It is fast and quick.", CATALOGUE);
    expect([two.score, two.quality]).toEqual([80, "good"]);
    expect(lint("The page shall load within 2 seconds.", CATALOGUE).issues).toEqual([]);
  });

  it("cuts the text into underlined runs", () => {
    const text = "Load fast now.";
    const parts = segments(text, lint(text, CATALOGUE).issues);
    expect(parts.map((part) => [part.text, part.issue?.ruleId ?? null])).toEqual([
      ["Load ", null],
      ["fast", "vague.speed"],
      [" now.", null],
    ]);
  });
});

describe("AuthoringPanel", () => {
  const render = (onUseWording = vi.fn()) =>
    renderWithProviders(
      <AuthoringPanel projectId="p1" text="The app should load the summary quickly." onUseWording={onUseWording} />,
    );

  it("shows the quality meter and the hints, and never blocks", async () => {
    mockApi({ "GET /api/v1/lint/catalogue": CATALOGUE });
    render();
    expect(await screen.findByLabelText(/Quality Good, 90 of 100/)).toBeInTheDocument();
    expect(screen.getByText(/Speed word without a number/)).toBeInTheDocument();
    expect(screen.getByText("Hints never block proposing.")).toBeInTheDocument();
  });

  it("runs a pre-flight dry run and draws the ghost node", async () => {
    const { calls } = mockApi({
      "GET /api/v1/lint/catalogue": CATALOGUE,
      "POST /api/v1/projects/p1/preflight": {
        status: "done",
        likely_findings: [
          { category: "Conflicting", requirement_id: "r14", label: "REQ-014", confidence: 0.82, rationale: "Different timeouts.", low_confidence: false },
        ],
        compared: ["r14"],
        llm_calls: 2,
        budget: { remaining: 411, monthly: 2000 },
        label: "AI",
      },
    });
    const { user } = render();
    await user.click(screen.getByRole("button", { name: "Run check" }));
    expect((await screen.findByText(/Likely conflicting/)).closest("li")).toHaveTextContent("with REQ-014");
    expect(screen.getByText("411 of 2000 analyses left this month.")).toBeInTheDocument();
    const map = screen.getByRole("img", { name: /the draft and 1 requirement it may affect/ });
    expect(within(map as unknown as HTMLElement).getByText("REQ-014")).toBeInTheDocument();
    expect(calls.find((call) => call.method === "POST")?.body).toContain("quickly");
  });

  it("says when the budget is spent", async () => {
    mockApi({
      "GET /api/v1/lint/catalogue": CATALOGUE,
      "POST /api/v1/projects/p1/preflight": { status: "budget", likely_findings: [], compared: [], llm_calls: 0, budget: { remaining: 0, monthly: 2000 }, label: "AI" },
    });
    const { user } = render();
    await user.click(screen.getByRole("button", { name: "Run check" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("budget is used up");
  });

  it("shows the AI wording as a diff and applies it only on Accept", async () => {
    mockApi({
      "GET /api/v1/lint/catalogue": CATALOGUE,
      "POST /api/v1/projects/p1/improve-wording": {
        original: "The app should load the summary quickly.",
        proposed: "The app shall display the summary within [TBD — confirm].",
        template: "ubiquitous",
        changes: ["Measurable"],
        tbd_slots: ["load time"],
        lint_before: 87,
        lint_after: 75,
        label: "AI",
      },
    });
    const onUse = vi.fn();
    const { user } = render(onUse);
    await user.click(screen.getByRole("button", { name: /Improve wording/ }));
    const diff = await screen.findByLabelText("Suggested wording, as a diff");
    expect(diff.querySelector("ins")).toHaveTextContent("display");
    expect(screen.getByText("Fill in before proposing: load time.")).toBeInTheDocument();
    expect(onUse).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(onUse).toHaveBeenCalledWith("The app shall display the summary within [TBD — confirm].");
    await waitFor(() => expect(screen.queryByLabelText("Suggested wording, as a diff")).not.toBeInTheDocument());
  });
});
