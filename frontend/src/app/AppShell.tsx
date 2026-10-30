import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { ProjectSwitcher } from "../features/projects/ProjectSwitcher";
import { Button } from "../components/Button";
import { useAuth } from "./auth";
import { usePermissions } from "./usePermissions";

const PROJECT_NAV = [
  { to: "", label: "Home", end: true },
  { to: "map", label: "Map" },
  { to: "requirements", label: "Requirements" },
  { to: "issues", label: "Issues" },
  { to: "changes", label: "Change requests" },
  { to: "baselines", label: "Baselines" },
  { to: "insights", label: "Insights" },
];

function initials(name: string | undefined): string {
  return (name ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** The app shell of the Home board: top bar with the workspace/project switcher, the sidebar
 *  with Project, Channels and Workspace groups, and the routed screen in the middle. */
export function AppShell() {
  const { workspaceId, projectId } = useParams();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { can } = usePermissions(projectId ? { projectId } : null);
  const projectBase = workspaceId && projectId ? `/w/${workspaceId}/p/${projectId}` : null;

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="logo" aria-label="Requirements Conflict Detector home">
          RCD
        </NavLink>
        <ProjectSwitcher workspaceId={workspaceId} projectId={projectId} />
        <div className="topbar-spacer" />
        <span className="muted" style={{ fontSize: 14 }}>
          {user?.full_name}
        </span>
        <button
          type="button"
          className="avatar"
          title="Sign out"
          aria-label={`Sign out ${user?.full_name ?? ""}`}
          onClick={() => {
            logout();
            navigate("/login");
          }}
        >
          {initials(user?.full_name)}
        </button>
      </header>

      <nav className="sidebar" aria-label="Main">
        {projectBase && can("req.propose") && (
          <Button variant="accent" onClick={() => navigate(`${projectBase}/requirements/new`)}>
            + New requirement
          </Button>
        )}
        {projectBase && (
          <div className="nav-group">
            <div className="eyebrow">Project</div>
            {PROJECT_NAV.map((item) => (
              <NavLink
                key={item.label}
                to={item.to ? `${projectBase}/${item.to}` : projectBase}
                end={item.end}
                className="nav-link"
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        )}
        {projectBase && (
          <div className="nav-group">
            <div className="eyebrow">Channels</div>
            <NavLink to={`${projectBase}/channels/general`} className="nav-link">
              # general
            </NavLink>
          </div>
        )}
        {workspaceId && (
          <div className="nav-group">
            <div className="eyebrow">Workspace</div>
            <NavLink to={`/w/${workspaceId}`} end className="nav-link">
              Projects
            </NavLink>
            <NavLink to={`/w/${workspaceId}/members`} className="nav-link">
              Members &amp; roles
            </NavLink>
          </div>
        )}
      </nav>

      <main className="main" id="main">
        <Outlet />
      </main>
    </div>
  );
}
