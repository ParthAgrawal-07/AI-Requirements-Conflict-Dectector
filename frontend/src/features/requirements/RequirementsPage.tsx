import { useState } from "react";
import { useParams } from "react-router-dom";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useDocuments, useProject } from "../projects/api";
import { DocumentProgressList, UploadDialog } from "../projects/UploadDialog";
import { RequirementsTable } from "./RequirementsTable";

/** Requirements board (US-01, US-03, US-04): upload, live extraction progress, the table. */
export function RequirementsPage() {
  const { projectId = "" } = useParams();
  useProjectRealtime(projectId);
  const project = useProject(projectId);
  const documents = useDocuments(projectId);
  const { can } = usePermissions({ projectId });
  const [uploading, setUploading] = useState(false);

  const docs = documents.data?.items ?? [];
  const inFlight = docs.filter((doc) => doc.status !== "done");
  const allFailed = docs.length > 0 && docs.every((doc) => doc.status === "failed");

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Requirements</h1>
          <p className="muted" style={{ margin: 0 }}>
            {project.data?.name}
          </p>
        </div>
        {(can("doc.upload") || can("baseline.manage")) && (
          <Button onClick={() => setUploading(true)}>Upload SRS</Button>
        )}
      </div>
      {inFlight.length > 0 && (
        <section aria-label="Uploads in progress" style={{ marginBottom: 24 }}>
          <DocumentProgressList documents={inFlight} />
        </section>
      )}
      <RequirementsTable projectId={projectId} extractionFailed={allFailed} />
      <UploadDialog projectId={projectId} open={uploading} onClose={() => setUploading(false)} />
    </div>
  );
}
