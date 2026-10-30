import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useDocuments, useProject } from "./api";
import { DocumentProgressList, UploadDialog } from "./UploadDialog";

/** Project home for Sprint 1: the project, its status, and its documents with live progress.
 *  The dashboard cards of the Home board arrive with US-13 (Sprint 5). */
export function ProjectHomePage() {
  const { workspaceId = "", projectId = "" } = useParams();
  useProjectRealtime(projectId);
  const { user } = useAuth();
  const project = useProject(projectId);
  const documents = useDocuments(projectId);
  const { can } = usePermissions({ projectId });
  const [uploading, setUploading] = useState(false);

  if (project.isLoading) return <p className="page">Loading project…</p>;
  if (!project.data) return <p className="page">This project does not exist or you have no access.</p>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="eyebrow">
            {project.data.name} · context v{project.data.context_version}
          </div>
          <h1>Hello, {user?.full_name.split(" ")[0]}</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {(can("doc.upload") || can("baseline.manage")) && (
            <Button onClick={() => setUploading(true)}>Upload SRS</Button>
          )}
          <Link className="btn btn-primary" to={`/w/${workspaceId}/p/${projectId}/requirements`}>
            View requirements
          </Link>
        </div>
      </div>

      <section className="card" style={{ padding: 20, marginBottom: 24 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Status</h2>
        {project.data.status === "active" ? (
          <Badge tone="approved">Active — analysis enabled</Badge>
        ) : (
          <Badge tone="proposed">Setup — analysis waits for the project context</Badge>
        )}
      </section>

      <section aria-label="Documents">
        <h2 style={{ fontSize: 18 }}>Documents</h2>
        {documents.data && documents.data.items.length === 0 ? (
          <p className="muted">No documents yet.</p>
        ) : (
          <DocumentProgressList documents={documents.data?.items ?? []} />
        )}
      </section>
      <UploadDialog projectId={projectId} open={uploading} onClose={() => setUploading(false)} />
    </div>
  );
}
