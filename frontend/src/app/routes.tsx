import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { LoginPage } from "../features/auth/LoginPage";
import { SignupWithCodePage } from "../features/auth/SignupWithCodePage";
import { ChannelView } from "../features/channels/ChannelView";
import { KitPage } from "../features/kit/KitPage";
import { JoinPage } from "../features/members/JoinPage";
import { MembersPage } from "../features/members/MembersPage";
import { WorkspaceCreate } from "../features/members/WorkspaceCreate";
import { lastProject, useWorkspaces } from "../features/projects/api";
import { ProjectHomePage } from "../features/projects/ProjectHomePage";
import { WorkspaceHomePage } from "../features/projects/WorkspaceHomePage";
import { prototypeRoutes } from "../features/prototypes/routes";
import { RequirementsPage } from "../features/requirements/RequirementsPage";
import { ProjectCreatePage } from "../features/setup/ProjectCreatePage";
import { ProjectSetupLayout } from "../features/setup/SetupBanner";
import { SetupWizard } from "../features/setup/SetupWizard";
import { WorkspaceActions } from "../features/setup/WorkspaceActions";
import { AppShell } from "./AppShell";
import { useAuth } from "./auth";
import { ComingSoon } from "./ComingSoon";

/** Routes behind sign-in; a signed-out visitor goes to /login and comes back afterwards. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { token, loading } = useAuth();
  const location = useLocation();
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  if (loading) return <p className="page">Loading…</p>;
  return <>{children ?? <Outlet />}</>;
}

/** "/" opens the last-used project (US-24), else the only workspace, else a hint. */
export function RootRedirect() {
  const workspaces = useWorkspaces();
  if (workspaces.isLoading) return <p className="page">Loading…</p>;
  const list = workspaces.data ?? [];
  const last = lastProject();
  if (last && list.some((workspace) => workspace.id === last.workspaceId)) {
    const target = last.projectId
      ? `/w/${last.workspaceId}/p/${last.projectId}`
      : `/w/${last.workspaceId}`;
    return <Navigate to={target} replace />;
  }
  if (list.length > 0) return <Navigate to={`/w/${list[0].id}`} replace />;
  return <NoWorkspace />;
}

export function NoWorkspace() {
  return (
    <div className="page">
      <h1>You are not in a workspace yet</h1>
      <p className="muted">
        Ask your project manager for a join code. If you are waiting for approval, your workspace
        appears here once a manager approves your request.
      </p>
      <p>
        <Link to="/join">I have a join code</Link>
      </p>
    </div>
  );
}

const LATER: { path: string; title: string; sprint: string }[] = [
  { path: "map", title: "Map", sprint: "Sprint 3 (US-14)" },
  { path: "issues", title: "Issues", sprint: "Sprint 4 (US-52)" },
  { path: "changes", title: "Change requests", sprint: "Sprint 4 (US-33)" },
  { path: "baselines", title: "Baselines", sprint: "Sprint 5 (US-40)" },
  { path: "insights", title: "Insights", sprint: "Sprint 5 (US-13)" },
  { path: "requirements/new", title: "New requirement", sprint: "Sprint 3 (US-30)" },
];

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  { path: "/signup", element: <SignupWithCodePage /> },
  { path: "/kit", element: <KitPage /> },
  { path: "/join", element: <JoinPage /> },
  { path: "/join/:code", element: <JoinPage /> },
  ...prototypeRoutes,
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <RootRedirect /> },
          { path: "/workspaces/new", element: <WorkspaceCreate /> },
          { path: "/w/:workspaceId", element: <WorkspaceHomePage actions={<WorkspaceActions />} /> },
          { path: "/w/:workspaceId/members", element: <MembersPage /> },
          { path: "/w/:workspaceId/projects/new", element: <ProjectCreatePage /> },
          {
            path: "/w/:workspaceId/p/:projectId",
            element: <ProjectSetupLayout />,
            children: [
              { index: true, element: <ProjectHomePage /> },
              { path: "setup", element: <SetupWizard /> },
              { path: "requirements", element: <RequirementsPage /> },
              { path: "channels/:channelId", element: <ChannelView /> },
              ...LATER.map((item) => ({
                path: item.path,
                element: <ComingSoon title={item.title} sprint={item.sprint} />,
              })),
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
];
