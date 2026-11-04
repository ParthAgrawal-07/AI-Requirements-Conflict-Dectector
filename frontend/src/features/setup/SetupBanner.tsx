import { Link, Outlet, useParams } from "react-router-dom";
import { useProject } from "../projects/api";
import { useProjectContext } from "./api";

/** "This project is in Setup" (US-60): shown on every project screen until the context is
 *  confirmed, naming what is missing. Members can still join and look around meanwhile. */
export function SetupBanner({ workspaceId, projectId }: { workspaceId: string; projectId: string }) {
  const project = useProject(projectId);
  const inSetup = project.data?.status === "setup";
  const context = useProjectContext(projectId);
  if (!inSetup) return null;

  const missing = context.data?.missing_fields ?? [];
  return (
    <div
      role="status"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "12px 32px",
        background: "var(--proposed-soft)",
        borderBottom: "1px dashed var(--proposed)",
      }}
    >
      <span style={{ flex: 1 }}>
        <strong>Setup:</strong> analysis, the composer and change requests start once the project
        context is confirmed.
        {missing.length > 0 && <> Missing: {missing.join(", ")}.</>}
      </span>
      <Link className="btn btn-sm" to={`/w/${workspaceId}/p/${projectId}/setup`}>
        Open setup
      </Link>
    </div>
  );
}

/** Wraps every project route so the banner appears above whichever screen is open. */
export function ProjectSetupLayout() {
  const { workspaceId = "", projectId = "" } = useParams();
  return (
    <>
      <SetupBanner workspaceId={workspaceId} projectId={projectId} />
      <Outlet />
    </>
  );
}
