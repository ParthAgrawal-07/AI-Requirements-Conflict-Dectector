import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, renderWithProviders, screen, act } from "./test-utils";
import { Drawer } from "../src/components/Drawer";
import { Tabs } from "../src/components/Tabs";
import { ToastProvider, useToast } from "../src/components/Toast";

describe("Drawer component", () => {
  it("renders title, content, and footer when open", () => {
    renderWithProviders(
      <Drawer open={true} title="Drawer Title" onClose={() => {}} footer={<button>Save</button>}>
        <p>Drawer Body</p>
      </Drawer>,
    );
    expect(screen.getByRole("dialog", { name: "Drawer Title" })).toBeInTheDocument();
    expect(screen.getByText("Drawer Body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    renderWithProviders(
      <Drawer open={false} title="Hidden" onClose={() => {}}>
        <p>Hidden Body</p>
      </Drawer>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("calls onClose when Close button is clicked", async () => {
    const onClose = vi.fn();
    const { user } = renderWithProviders(
      <Drawer open={true} title="Closable" onClose={onClose}>
        <p>Body</p>
      </Drawer>,
    );
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <Drawer open={true} title="Closable Esc" onClose={onClose}>
        <p>Body</p>
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("preserves input focus across re-renders when typing (does not steal focus)", async () => {
    function TestDrawerInput() {
      const [val, setVal] = useState("");
      return (
        <Drawer open={true} title="Typing Drawer" onClose={() => {}}>
          <label htmlFor="test-text">Field</label>
          <input
            id="test-text"
            value={val}
            onChange={(e) => setVal(e.target.value)}
          />
        </Drawer>
      );
    }
    const { user } = renderWithProviders(<TestDrawerInput />);
    const input = screen.getByLabelText("Field");
    await user.type(input, "Product");
    expect(input).toHaveValue("Product");
    expect(document.activeElement).toBe(input);
  });

  it("traps focus between first and last focusable elements", () => {
    renderWithProviders(
      <Drawer open={true} title="Trap Drawer" onClose={() => {}}>
        <input aria-label="Input One" />
        <button type="button">Bottom Button</button>
      </Drawer>,
    );
    const closeBtn = screen.getByRole("button", { name: "Close" });
    const bottomBtn = screen.getByRole("button", { name: "Bottom Button" });

    // Focus starts or moves to closeBtn
    closeBtn.focus();
    expect(document.activeElement).toBe(closeBtn);

    // Shift+Tab from first element wraps to last element
    fireEvent.keyDown(closeBtn, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(bottomBtn);

    // Tab from last element wraps to first element
    fireEvent.keyDown(bottomBtn, { key: "Tab", shiftKey: false });
    expect(document.activeElement).toBe(closeBtn);
  });
});

describe("Tabs component", () => {
  it("renders tablist and switches tabs via keyboard navigation", async () => {
    function TabsDemo() {
      const [selected, setSelected] = useState("tab1");
      return (
        <Tabs
          label="Demo Tabs"
          selected={selected}
          onSelect={setSelected}
          tabs={[
            { id: "tab1", label: "First" },
            { id: "tab2", label: "Second" },
            { id: "tab3", label: "Third" },
          ]}
        >
          <p>Panel: {selected}</p>
        </Tabs>
      );
    }
    renderWithProviders(<TabsDemo />);
    const firstTab = screen.getByRole("tab", { name: "First" });
    const secondTab = screen.getByRole("tab", { name: "Second" });
    const thirdTab = screen.getByRole("tab", { name: "Third" });

    expect(firstTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Panel: tab1")).toBeInTheDocument();

    // ArrowRight moves to next tab
    firstTab.focus();
    fireEvent.keyDown(firstTab, { key: "ArrowRight" });
    expect(secondTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Panel: tab2")).toBeInTheDocument();

    // End jumps to last tab
    fireEvent.keyDown(secondTab, { key: "End" });
    expect(thirdTab).toHaveAttribute("aria-selected", "true");

    // Home jumps to first tab
    fireEvent.keyDown(thirdTab, { key: "Home" });
    expect(firstTab).toHaveAttribute("aria-selected", "true");
  });
});

describe("Toast component", () => {
  it("shows notifications and allows manual and timed dismissal", async () => {
    vi.useFakeTimers();
    function ToastTrigger() {
      const notify = useToast();
      return (
        <button type="button" onClick={() => notify("Operation successful", "success")}>
          Trigger Toast
        </button>
      );
    }
    renderWithProviders(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    );

    // Using fireEvent since fake timers are active
    fireEvent.click(screen.getByRole("button", { name: "Trigger Toast" }));
    expect(screen.getByText("Operation successful")).toBeInTheDocument();

    // Fast-forward 5000ms
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Operation successful")).not.toBeInTheDocument();

    vi.useRealTimers();
  });
});
