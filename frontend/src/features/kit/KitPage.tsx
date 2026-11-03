import { useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { Tabs } from "../../components/Tabs";
import { useToast } from "../../components/Toast";

/** The shared component kit on one page (Sprint 0 check: "a kit page shows each component").
 *  Open /kit in the dev server; no sign-in needed, no data used. */
export function KitPage() {
  const notify = useToast();
  const [drawer, setDrawer] = useState(false);
  const [tab, setTab] = useState("members");

  return (
    <div className="page grid-paper" style={{ minHeight: "100%" }}>
      <h1>Component kit</h1>

      <h2>Buttons</h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button variant="primary">Primary</Button>
        <Button>Secondary</Button>
        <Button variant="accent">+ New requirement</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Revoke</Button>
        <Button loading>Saving</Button>
        <Button size="sm">Small</Button>
      </div>

      <h2>Badges — icon plus word, never colour alone</h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Badge tone="approved">Approved v2</Badge>
        <Badge tone="proposed">Proposed</Badge>
        <Badge tone="conflict">conflict</Badge>
        <Badge tone="neutral">Deprecated</Badge>
        <Badge tone="ai">Suggested</Badge>
        <Badge tone="info">needs review</Badge>
        <Badge tone="neutral" icon="⚑">
          protected
        </Badge>
      </div>

      <h2>Tabs</h2>
      <Tabs
        label="Kit tabs"
        selected={tab}
        onSelect={setTab}
        tabs={[
          { id: "members", label: "Members" },
          { id: "roles", label: "Roles" },
          { id: "codes", label: "Join codes" },
        ]}
      >
        <p>Panel for “{tab}”. Use the arrow keys to move between tabs.</p>
      </Tabs>

      <h2>Drawer and toast</h2>
      <div style={{ display: "flex", gap: 8 }}>
        <Button onClick={() => setDrawer(true)}>Open drawer</Button>
        <Button onClick={() => notify("Saved.", "success")}>Success toast</Button>
        <Button onClick={() => notify("Something failed.", "error")}>Error toast</Button>
      </div>
      <Drawer open={drawer} title="Drawer" onClose={() => setDrawer(false)}>
        <p>Escape, the backdrop or Close dismiss it; focus returns to the button.</p>
      </Drawer>
    </div>
  );
}
