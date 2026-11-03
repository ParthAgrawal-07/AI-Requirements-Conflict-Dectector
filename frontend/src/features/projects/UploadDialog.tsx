import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../api/client";
import type { DocumentRead, ImportMode } from "../../api/types";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/Toast";
import { useUploadDocument } from "./api";

const ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export interface UploadDialogProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
}

/** Upload an SRS (US-01). Baseline import is offered only to members with baseline.manage;
 *  the server checks it again. Progress then shows in DocumentProgressList. */
export function UploadDialog({ projectId, open, onClose }: UploadDialogProps) {
  const { can } = usePermissions({ projectId });
  const upload = useUploadDocument(projectId);
  const notify = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<ImportMode>("proposals");
  const [group, setGroup] = useState("");
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setFile(null);
    setError(null);
    setImportMode("proposals");
    setGroup("");
    onClose();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      setError("Choose a PDF or Word file first.");
      return;
    }
    setError(null);
    try {
      const document = await upload.mutateAsync({ file, importMode, stakeholderGroup: group });
      notify(
        document.duplicate_of
          ? `${document.filename} uploaded. The same file was uploaded before.`
          : `${document.filename} uploaded. Extracting requirements…`,
        "success",
      );
      close();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Upload failed. Try again.");
    }
  };

  return (
    <Drawer
      open={open}
      title="Upload SRS"
      onClose={close}
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" type="submit" form="upload-form" loading={upload.isPending}>
            Upload
          </Button>
        </>
      }
    >
      <form id="upload-form" onSubmit={submit}>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="field">
          <label htmlFor="upload-file">Document</label>
          <input
            id="upload-file"
            type="file"
            accept={ACCEPT}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <span className="field-hint">PDF or Word (.docx), up to 25 MB.</span>
        </div>
        <fieldset className="field" style={{ border: "none", padding: 0 }}>
          <legend>Import as</legend>
          <label>
            <input
              type="radio"
              name="import-mode"
              value="proposals"
              checked={importMode === "proposals"}
              onChange={() => setImportMode("proposals")}
            />{" "}
            Proposals — requirements start as Proposed and are reviewed
          </label>
          {can("baseline.manage") && (
            <label>
              <input
                type="radio"
                name="import-mode"
                value="baseline"
                checked={importMode === "baseline"}
                onChange={() => setImportMode("baseline")}
              />{" "}
              Baseline — requirements are already agreed (Approved)
            </label>
          )}
        </fieldset>
        <div className="field">
          <label htmlFor="upload-group">Stakeholder group (optional)</label>
          <input
            id="upload-group"
            className="input"
            maxLength={120}
            value={group}
            onChange={(event) => setGroup(event.target.value)}
          />
        </div>
      </form>
    </Drawer>
  );
}

const STATUS_LABEL: Record<DocumentRead["status"], string> = {
  queued: "Queued",
  processing: "Processing",
  done: "Complete",
  failed: "Failed",
};

/** Live progress of the project's uploads (US-03): status, percentage, and the failed stage. */
export function DocumentProgressList({ documents }: { documents: DocumentRead[] }) {
  if (documents.length === 0) return null;
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
      {documents.map((doc) => (
        <li key={doc.document_id} className="card" style={{ padding: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <strong>{doc.filename}</strong>
            <span className="mono muted">
              {STATUS_LABEL[doc.status]}
              {doc.status === "done" ? ` · ${doc.requirement_count} requirements` : ""}
            </span>
          </div>
          {(doc.status === "queued" || doc.status === "processing") && (
            <div
              className="progress"
              role="progressbar"
              aria-label={`${doc.filename} progress`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={doc.progress_percent}
              style={{ marginTop: 8 }}
            >
              <span style={{ width: `${doc.progress_percent}%` }} />
            </div>
          )}
          {doc.status === "failed" && doc.error_message && (
            <p className="field-error" style={{ margin: "8px 0 0" }}>
              {doc.error_message}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
