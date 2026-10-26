import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "./test-utils";

// Smoke test: proves Vitest + jsdom + React Testing Library + jest-dom
// matchers + user-event are wired together. Safe to keep or delete once
// real component tests exist.
describe("test harness smoke test", () => {
  it("renders and is queryable by role", () => {
    renderWithProviders(<button type="button">Upload</button>);
    expect(screen.getByRole("button", { name: /upload/i })).toBeInTheDocument();
  });

  it("supports user interaction", async () => {
    const onClick = vi.fn();
    const { user } = renderWithProviders(<button onClick={onClick}>Go</button>);
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
