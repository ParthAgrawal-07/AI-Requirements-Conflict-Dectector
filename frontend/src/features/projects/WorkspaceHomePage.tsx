import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "../../components/Badge";
import { useProjects, useWorkspaces } from "./api";

/** A workspace's projects. "New project" and the setup wizard come from features/setup. */
export function WorkspaceHomePage({ actions }: { actions?: ReactNode }) {
  const { workspaceId = "" } = useParams();
  const workspaces = useWorkspaces();
  const projects = useProjects(workspaceId);
  const workspace = workspaces.data?.find((item) => item.id === workspaceId);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>{workspace?.name ?? "Workspace"}</h1>
          <p className="muted" style={{ margin: 0 }}>
            {projects.data ? `${projects.data.total} projects` : ""}
            {workspace ? ` · your role: ${workspace.role.name}` : ""}
          </p>
        </div>
        {actions}
      </div>
      {projects.data?.items.length === 0 && (
        <p className="empty-state card">No projects yet.</p>
      )}
      <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 12 }}>
        {projects.data?.items.map((project) => (
          <li key={project.id} className="card" style={{ padding: 16 }}>
            <Link to={`/w/${workspaceId}/p/${project.id}`} style={{ fontWeight: 600 }}>
              {project.name}
            </Link>{" "}
            {project.status === "setup" ? (
              <Badge tone="proposed">Setup</Badge>
            ) : (
              <Badge tone="approved">Active</Badge>
            )}
            {project.description && <p className="muted">{project.description}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
