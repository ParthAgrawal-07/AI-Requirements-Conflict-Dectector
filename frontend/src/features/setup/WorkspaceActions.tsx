import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { usePermissions } from "../../app/usePermissions";

/** "New project" / "New workspace" on the workspace page (US-24), shown only to those allowed. */
export function WorkspaceActions() {
  const { workspaceId = "" } = useParams();
  const { user } = useAuth();
  const { can } = usePermissions({ workspaceId });
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {user?.platform_role === "platform_admin" && (
        <Link className="btn" to="/workspaces/new">
          New workspace
        </Link>
      )}
      {can("project.manage") && (
        <Link className="btn btn-primary" to={`/w/${workspaceId}/projects/new`}>
          New project
        </Link>
      )}
    </div>
  );
}
