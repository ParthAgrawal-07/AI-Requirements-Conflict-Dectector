import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { renderWithProviders, screen } from "./test-utils";
import App from "../src/App";

describe("Application end-to-end frontend smoke test", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  it("renders the shared application shell and default findings page", () => {
    renderWithProviders(<App />);

    // TopNav branding & user
    expect(
      screen.getByText("Requirements Conflict Detector")
    ).toBeInTheDocument();
    expect(screen.getByText("Atlas · Customer Portal")).toBeInTheDocument();
    expect(screen.getByText("Abhijeet")).toBeInTheDocument();
    expect(screen.getByText("Reviewer")).toBeInTheDocument();

    // Findings Page header & KPIs
    expect(screen.getByRole("heading", { name: "Findings" })).toBeInTheDocument();
    expect(screen.getByText("Total findings")).toBeInTheDocument();
    expect(screen.getByText("Pending review")).toBeInTheDocument();
    expect(screen.getByText("High severity")).toBeInTheDocument();
    expect(screen.getByText("Awaiting clarification")).toBeInTheDocument();

    // Sample findings present in table
    expect(screen.getByText("F-001")).toBeInTheDocument();
    expect(screen.getByText(/5-minute inactivity logout/i)).toBeInTheDocument();
  });

  it("navigates into Conflict Review when 'Review Finding' is clicked", async () => {
    const { user } = renderWithProviders(<App />);

    const reviewButtons = screen.getAllByRole("button", {
      name: /review finding/i,
    });
    expect(reviewButtons.length).toBeGreaterThan(0);

    await user.click(reviewButtons[0]);

    // Review page header & requirement cards
    expect(
      screen.getByRole("heading", { name: /review possible session conflict/i })
    ).toBeInTheDocument();
    expect(screen.getByText("R12")).toBeInTheDocument();
    expect(screen.getByText("R27")).toBeInTheDocument();
    expect(screen.getByText("Choose a review action")).toBeInTheDocument();
  });

  it("navigates into Clarification Page when 'Request Clarification' is clicked", async () => {
    const { user } = renderWithProviders(<App />);

    // Navigate to review first
    const reviewButtons = screen.getAllByRole("button", {
      name: /review finding/i,
    });
    await user.click(reviewButtons[0]);

    // Click Request Clarification
    const clarifyBtn = screen.getByRole("button", {
      name: /request clarification/i,
    });
    await user.click(clarifyBtn);

    // Verify clarification view loaded
    expect(
      screen.getByRole("heading", { name: /clarify session behavior/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/AI-Generated Question · Editorial Review Required/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /submit clarification/i })
    ).toBeInTheDocument();
  });

  it("allows navigating to other sections via the sidebar", async () => {
    const { user } = renderWithProviders(<App />);

    const showcaseLink = screen.getByRole("button", { name: /ui showcase/i });
    await user.click(showcaseLink);

    expect(
      screen.getByRole("heading", { name: "UI Component Library" })
    ).toBeInTheDocument();
  });
});
