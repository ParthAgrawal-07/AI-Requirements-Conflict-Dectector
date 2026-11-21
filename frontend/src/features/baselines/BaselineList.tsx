import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useBaselines, useFreezeBaseline } from "./api";
import { CompareView } from "./CompareView";

/** Baselines (US-40): labelled, frozen snapshots of the agreed requirements, and the comparison
 *  of any two ("v1.1" against "v1.0"). Freezing needs ``baseline.manage``. */
export function BaselineList() {
  const { projectId = "" } = useParams();
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const baselines = useBaselines(projectId);
  const freeze = useFreezeBaseline(projectId);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [base, setBase] = useState<string | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const list = baselines.data ?? [];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!label.trim()) return;
    freeze.mutate(
      { label: label.trim(), note: note.trim() || undefined },
      {
        onSuccess: (created) => {
          notify(`Baseline ${created.label} frozen with ${created.requirement_count} requirements`, "success");
          setLabel("");
          setNote("");
        },
        onError: (error) => notify(error instanceof ApiError ? error.message : "Could not freeze the baseline", "error"),
      },
    );
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Baselines</h1>
          <p className="muted" style={{ margin: 0 }}>
            Frozen snapshots of the approved and implemented requirements. Snapshots never change.
          </p>
        </div>
      </header>

      {can("baseline.manage") && (
        <form className="inline-form" onSubmit={submit} aria-label="Freeze a baseline">
          <label>
            Label{" "}
            <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="v1.1" maxLength={80} required />
          </label>
          <label>
            Note{" "}
            <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Sign-off with the client" />
          </label>
          <Button variant="primary" type="submit" loading={freeze.isPending}>
            Freeze baseline
          </Button>
        </form>
      )}

      {baselines.isLoading && <p className="muted">Loading…</p>}
      {!baselines.isLoading && list.length === 0 && <p className="muted">No baselines yet.</p>}
      {list.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Label</th>
              <th scope="col">Requirements</th>
              <th scope="col">Baseline revision</th>
              <th scope="col">Frozen by</th>
              <th scope="col">When</th>
              <th scope="col">Compare</th>
            </tr>
          </thead>
          <tbody>
            {list.map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>{row.label}</strong>
                  {row.note && <div className="muted small">{row.note}</div>}
                </td>
                <td>{row.requirement_count}</td>
                <td>{row.baseline_revision}</td>
                <td>{row.created_by_name ?? "—"}</td>
                <td>{new Date(row.created_at).toLocaleString()}</td>
                <td>
                  <label>
                    <input type="radio" name="base" checked={base === row.id} onChange={() => setBase(row.id)} /> from
                  </label>{" "}
                  <label>
                    <input type="radio" name="target" checked={target === row.id} onChange={() => setTarget(row.id)} /> to
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {list.length > 1 && <CompareView base={base} target={target} />}
    </div>
  );
}
