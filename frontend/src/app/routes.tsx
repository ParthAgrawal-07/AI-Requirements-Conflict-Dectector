import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { Button } from "../components/Button";
import { LoginPage } from "../features/auth/LoginPage";
import { SignupWithCodePage } from "../features/auth/SignupWithCodePage";
import { ChangeEditor } from "../features/changes/ChangeEditor";
import { ChangeRequestList } from "../features/changes/ChangeRequestList";
import { ChangeRequestPage } from "../features/changes/ChangeRequestPage";
import { ChannelView } from "../features/channels/ChannelView";
import { ComposerPage } from "../features/composer/ComposerPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { FindingsPage } from "../features/findings/FindingsPage";
import { IssueList } from "../features/issues/IssueList";
import { IssuePage } from "../features/issues/IssuePage";
import { KitPage } from "../features/kit/KitPage";
import { JoinPage } from "../features/members/JoinPage";
import { MembersPage } from "../features/members/MembersPage";
import { WorkspaceCreate } from "../features/members/WorkspaceCreate";
import { MapPage } from "../features/map/MapPage";
import { Inbox } from "../features/notifications/Inbox";
import { lastProject, useProjects, useWorkspaces } from "../features/projects/api";
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
  const { token, loading, restoring } = useAuth();
  const location = useLocation();
  if (restoring) return <p className="page">Loading…</p>;
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  if (loading) return <p className="page">Loading…</p>;
  return <>{children ?? <Outlet />}</>;
}

/** "/" opens the last-used project (US-24), else the only workspace, else a hint. */
export function RootRedirect() {
  const workspaces = useWorkspaces();
  const last = lastProject();
  const projects = useProjects(last?.workspaceId);

  if (workspaces.isLoading || (Boolean(last?.projectId) && projects.isLoading)) {
    return <p className="page">Loading…</p>;
  }

  if (workspaces.isError) {
    return (
      <div className="page" role="alert">
        <h1>Could not load workspaces</h1>
        <p className="field-error">
          {workspaces.error instanceof Error ? workspaces.error.message : "Failed to load workspaces."}
        </p>
        <Button onClick={() => void workspaces.refetch()}>Try again</Button>
      </div>
    );
  }

  const list = workspaces.data ?? [];
  if (last && list.some((workspace) => workspace.id === last.workspaceId)) {
    const projectExists =
      Boolean(last.projectId) &&
      Boolean(projects.data?.items.some((p) => p.id === last.projectId));
    const target = projectExists
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
  { path: "baselines", title: "Baselines", sprint: "Sprint 5 (US-40)" },
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
          { path: "/inbox", element: <Inbox /> },
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
              { path: "requirements/new", element: <ComposerPage /> },
              { path: "channels/:channelId", element: <ChannelView /> },
              { path: "findings", element: <FindingsPage /> },
              { path: "map", element: <MapPage /> },
              { path: "issues", element: <IssueList /> },
              { path: "issues/:issueId", element: <IssuePage /> },
              { path: "changes", element: <ChangeRequestList /> },
              { path: "changes/new", element: <ChangeEditor /> },
              { path: "changes/:changeRequestId", element: <ChangeRequestPage /> },
              { path: "insights", element: <DashboardPage /> },
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
