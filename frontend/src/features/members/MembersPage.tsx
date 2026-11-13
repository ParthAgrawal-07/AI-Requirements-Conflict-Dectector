import { useState } from "react";
import { useParams } from "react-router-dom";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Tabs } from "../../components/Tabs";
import { useWorkspaces } from "../projects/api";
import { useRoles } from "./api";
import { JoinCodesTab } from "./JoinCodesTab";

/** Members & roles board. Sprint 1: Roles and Join codes; the member list with role changes and
 *  removal arrives with US-26 (Sprint 2). Tabs a member cannot use are not shown. */
export function MembersPage() {
  const { workspaceId = "" } = useParams();
  const workspace = useWorkspaces().data?.find((item) => item.id === workspaceId);
  const { can } = usePermissions({ workspaceId });
  const tabs = [
    { id: "members", label: "Members" },
    { id: "roles", label: "Roles" },
    ...(can("joincode.manage") ? [{ id: "codes", label: "Join codes" }] : []),
  ];
  const [tab, setTab] = useState("roles");

  return (
    <div className="page">
      <div className="page-header">
        <h1>{workspace?.name ?? "Workspace"} workspace</h1>
      </div>
      <Tabs label="Members and roles" tabs={tabs} selected={tab} onSelect={setTab}>
        {tab === "members" && (
          <p className="empty-state card">
            The member list, role changes and removal arrive with US-26 (Sprint 2).
          </p>
        )}
        {tab === "roles" && <RolesTab workspaceId={workspaceId} />}
        {tab === "codes" && <JoinCodesTab workspaceId={workspaceId} />}
      </Tabs>
    </div>
  );
}

function RolesTab({ workspaceId }: { workspaceId: string }) {
  const roles = useRoles(workspaceId);
  return (
    <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 12 }}>
      {roles.data?.map((role) => (
        <li key={role.id} className="card" style={{ padding: 16 }}>
          <strong>{role.name}</strong>{" "}
          {role.is_default ? <Badge>default</Badge> : <Badge tone="info">custom</Badge>}{" "}
          {!role.grantable_by_join_code && <Badge tone="neutral">not by join code</Badge>}
          {role.description && <p className="muted">{role.description}</p>}
          <details>
            <summary>{role.permissions.length} permissions</summary>
            <p className="mono" style={{ fontSize: 13 }}>
              {role.permissions.join(" · ")}
            </p>
          </details>
        </li>
      ))}
    </ul>
  );
}
