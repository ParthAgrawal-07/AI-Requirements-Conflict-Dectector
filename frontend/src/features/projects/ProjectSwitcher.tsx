import { useNavigate } from "react-router-dom";
import { rememberLastProject, useProjects, useWorkspaces } from "./api";

export interface ProjectSwitcherProps {
  workspaceId?: string;
  projectId?: string;
}

/** "Acme Bank / Mobile Banking" in the top bar (US-24): switch workspace, then project. */
export function ProjectSwitcher({ workspaceId, projectId }: ProjectSwitcherProps) {
  const navigate = useNavigate();
  const workspaces = useWorkspaces();
  const projects = useProjects(workspaceId);

  const openWorkspace = (id: string) => {
    rememberLastProject(id);
    navigate(`/w/${id}`);
  };
  const openProject = (id: string) => {
    if (!workspaceId) return;
    rememberLastProject(workspaceId, id);
    navigate(`/w/${workspaceId}/p/${id}`);
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <label className="visually-hidden" htmlFor="switch-workspace">
        Workspace
      </label>
      <select
        id="switch-workspace"
        className="select"
        value={workspaceId ?? ""}
        onChange={(event) => openWorkspace(event.target.value)}
      >
        {!workspaceId && <option value="">Choose a workspace</option>}
        {workspaces.data?.map((workspace) => (
          <option key={workspace.id} value={workspace.id}>
            {workspace.name}
          </option>
        ))}
      </select>
      {workspaceId && (
        <>
          <span aria-hidden="true" className="muted">
            /
          </span>
          <label className="visually-hidden" htmlFor="switch-project">
            Project
          </label>
          <select
            id="switch-project"
            className="select"
            value={projectId ?? ""}
            onChange={(event) => openProject(event.target.value)}
          >
            {!projectId && <option value="">Choose a project</option>}
            {projects.data?.items.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
                {project.status === "setup" ? " (Setup)" : ""}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}
