import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { downloadTrail, KIND_TEXT, STATUS_TEXT, useComplianceQueue, type QueueItem } from "./api";
import { ProtectedBadge } from "./ProtectedBadge";

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

/** The compliance queue (Abhijeet — US-18, FR-36, NFR-13; interface design §14): what waits for a
 *  compliance reviewer — findings to decide, change requests to approve, requirements to sign
 *  off — then every protected requirement with its sign-off, and the audit trail as CSV or JSON. */
export function ComplianceQueue() {
  const { workspaceId = "", projectId = "" } = useParams();
  const { can, isLoading } = usePermissions({ projectId });
  const allowed = can("protected.signoff") || can("req.protect") || can("audit.export");
  const queue = useComplianceQueue(projectId, allowed);
  const notify = useToast();
  const [exporting, setExporting] = useState<string | null>(null);
  const base = `/w/${workspaceId}/p/${projectId}`;

  const href = (item: QueueItem): string => {
    if (item.kind === "finding") return `${base}/findings?finding=${item.id}`;
    if (item.kind === "change_request") return `${base}/changes/${item.id}`;
    return `${base}/map?focus=${item.requirement_ids[0] ?? ""}`;
  };
  const exportTrail = async (format: "csv" | "json") => {
    setExporting(format);
    try {
      await downloadTrail(projectId, format);
      notify("Audit trail exported — the export itself is recorded", "success");
    } catch (error) {
      notify(error instanceof ApiError ? error.message : "The export failed", "error");
    } finally {
      setExporting(null);
    }
  };

  if (isLoading) return <p className="page muted">Loading…</p>;
  if (!allowed) {
    return (
      <div className="page">
        <h1>Compliance</h1>
        <p className="muted">Only compliance reviewers and project managers see the compliance queue.</p>
      </div>
    );
  }
  const data = queue.data;
  return (
    <div className="page compliance-page">
      <header className="page-header">
        <div>
          <h1>Compliance</h1>
          <p className="muted small">
            Protected requirements are never resolved automatically: each decision here is a person&apos;s, and
            is audited.
          </p>
        </div>
        {can("audit.export") && (
          <div className="row-actions" role="group" aria-label="Export the audit trail">
            <Button size="sm" loading={exporting === "csv"} onClick={() => void exportTrail("csv")}>
              Audit trail CSV
            </Button>
            <Button size="sm" variant="ghost" loading={exporting === "json"} onClick={() => void exportTrail("json")}>
              JSON
            </Button>
          </div>
        )}
      </header>
      {queue.isLoading && <p className="muted">Loading…</p>}
      {queue.isError && <p role="alert">The compliance queue could not be loaded.</p>}
      {data && (
        <>
          <section aria-labelledby="queue-pending">
            <h2 id="queue-pending">Waiting for compliance ({data.pending.length})</h2>
            {data.pending.length === 0 ? (
              <p className="muted">Nothing is waiting.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">What</th>
                    <th scope="col">Requirements</th>
                    <th scope="col">Status</th>
                    <th scope="col">Since</th>
                  </tr>
                </thead>
                <tbody>
                  {data.pending.map((item) => (
                    <tr key={`${item.kind}-${item.id}`}>
                      <td>
                        <span className="muted small">{KIND_TEXT[item.kind]}</span>{" "}
                        <Link to={href(item)}>{item.title}</Link>
                      </td>
                      <td className="mono">{item.labels.join(", ")}</td>
                      <td>
                        {STATUS_TEXT[item.status]}
                        {item.done_by_name && <span className="muted small"> · {item.done_by_name}</span>}
                      </td>
                      <td>{when(item.since)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
          <section aria-labelledby="queue-protected">
            <h2 id="queue-protected">Protected requirements ({data.protected.length})</h2>
            {data.protected.length === 0 ? (
              <p className="muted">No requirement is protected yet. Mark one from its drawer on the map.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Requirement</th>
                    <th scope="col">State</th>
                    <th scope="col">Sign-off</th>
                    <th scope="col">Protected</th>
                  </tr>
                </thead>
                <tbody>
                  {data.protected.map((row) => {
                    const current = row.signed_off_version === row.current_version;
                    return (
                      <tr key={row.requirement_id}>
                        <td>
                          <Link className="mono" to={`${base}/map?focus=${row.requirement_id}`}>
                            {row.label}
                          </Link>{" "}
                          <ProtectedBadge reason={row.protection_reason} compact />
                        </td>
                        <td>
                          {row.state.replace("_", " ")} · v{row.current_version}
                        </td>
                        <td>
                          <span aria-hidden="true">{current ? "✓ " : "✗ "}</span>
                          {row.signed_off_version === null
                            ? "Not signed off"
                            : current
                              ? `Signed off v${row.signed_off_version}`
                              : `Signed off v${row.signed_off_version} — v${row.current_version} needs sign-off`}
                          {row.signed_off_by_name && <span className="muted small"> · {row.signed_off_by_name}</span>}
                        </td>
                        <td>
                          {when(row.protected_at)}
                          {row.protected_by_name && <span className="muted small"> · {row.protected_by_name}</span>}
                          {row.protection_reason && <div className="muted small">{row.protection_reason}</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
