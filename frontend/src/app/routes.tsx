import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { LoginPage } from "../features/auth/LoginPage";
import { SignupWithCodePage } from "../features/auth/SignupWithCodePage";
import { BaselineList } from "../features/baselines/BaselineList";
import { ChangeEditor } from "../features/changes/ChangeEditor";
import { ChangeRequestList } from "../features/changes/ChangeRequestList";
import { ChangeRequestPage } from "../features/changes/ChangeRequestPage";
import { ChannelView } from "../features/channels/ChannelView";
import { ComposerPage } from "../features/composer/ComposerPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { AiFeedbackPage } from "../features/feedback/AiFeedbackPage";
import { FindingsPage } from "../features/findings/FindingsPage";
import { IssueList } from "../features/issues/IssueList";
import { IssuePage } from "../features/issues/IssuePage";
import { KitPage } from "../features/kit/KitPage";
import { ProjectSettings } from "../features/members/ProjectSettings";
import { JoinPage } from "../features/members/JoinPage";
import { MembersPage } from "../features/members/MembersPage";
import { WorkspaceCreate } from "../features/members/WorkspaceCreate";
import { MapPage } from "../features/map/MapPage";
import { Inbox } from "../features/notifications/Inbox";
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

/** "/" opens the last-used project (US-24), else the only workspace. With none, a platform
 *  admin (who may create one) goes straight to creating it; anyone else sees how to join. */
export function RootRedirect() {
  const { user } = useAuth();
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
  if (user?.platform_role === "platform_admin") return <Navigate to="/workspaces/new" replace />;
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
              { path: "insights/ai-feedback", element: <AiFeedbackPage /> },
              { path: "baselines", element: <BaselineList /> },
              { path: "settings", element: <ProjectSettings /> },
              { path: "settings/decision-rules", element: <ProjectSettings tab="decision-rules" /> },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
];
