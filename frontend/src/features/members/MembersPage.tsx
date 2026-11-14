import { useState } from "react";
import { useParams } from "react-router-dom";
import { usePermissions } from "../../app/usePermissions";
import { Tabs } from "../../components/Tabs";
import { useWorkspaces } from "../projects/api";
import { JoinCodesTab } from "./JoinCodesTab";
import { MembersTab } from "./MembersTab";
import { RolesTab } from "./RolesTab";

/** Members & roles board (US-24, US-25, US-26, US-49): members, roles and custom roles, and join
 *  codes. Tabs a member cannot use are not shown; every action is checked by the server too. */
export function MembersPage() {
  const { workspaceId = "" } = useParams();
  const workspace = useWorkspaces().data?.find((item) => item.id === workspaceId);
  const { can } = usePermissions({ workspaceId });
  const tabs = [
    { id: "members", label: "Members" },
    { id: "roles", label: "Roles" },
    ...(can("joincode.manage") ? [{ id: "codes", label: "Join codes" }] : []),
  ];
  const [tab, setTab] = useState("members");

  return (
    <div className="page">
      <div className="page-header">
        <h1>{workspace?.name ?? "Workspace"} workspace</h1>
      </div>
      <Tabs label="Members and roles" tabs={tabs} selected={tab} onSelect={setTab}>
        {tab === "members" && <MembersTab workspaceId={workspaceId} />}
        {tab === "roles" && <RolesTab workspaceId={workspaceId} />}
        {tab === "codes" && <JoinCodesTab workspaceId={workspaceId} />}
      </Tabs>
    </div>
  );
}
