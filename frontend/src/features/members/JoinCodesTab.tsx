import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../api/client";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useProjects } from "../projects/api";
import {
  useCreateJoinCode,
  useJoinCodes,
  useRevokeJoinCode,
  useRoles,
  type CreatedJoinCode,
  type JoinCode,
  type JoinCodeInput,
} from "./api";
import { JoinRequestsTab } from "./JoinRequestsTab";

const STATUS_TEXT: Record<JoinCode["status"], string> = {
  active: "",
  revoked: "revoked",
  expired: "expired",
  exhausted: "used up",
};

export function joinLink(code: string, origin: string = window.location.origin): string {
  return `${origin}/join/${encodeURIComponent(code)}`;
}

const dateFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });

/** Join codes tab of the Members board (US-25): create, show once, copy, list, revoke; the join
 *  requests panel sits beside it. Codes never offer Owner or Admin (the API refuses them too). */
export function JoinCodesTab({ workspaceId }: { workspaceId: string }) {
  const roles = useRoles(workspaceId);
  const projects = useProjects(workspaceId);
  const codes = useJoinCodes(workspaceId);
  const create = useCreateJoinCode(workspaceId);
  const revoke = useRevokeJoinCode(workspaceId);
  const notify = useToast();

  const grantable = (roles.data ?? []).filter((role) => role.grantable_by_join_code);
  const [form, setForm] = useState({
    projectId: "",
    roleId: "",
    days: 7 as JoinCodeInput["expires_in_days"],
    maxUses: "20",
    approval: false,
  });
  const [created, setCreated] = useState<CreatedJoinCode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const roleId = form.roleId || grantable.find((role) => role.name === "Developer")?.id || "";
  const projectName = (id: string | null) =>
    id ? projects.data?.items.find((project) => project.id === id)?.name ?? "Project" : "Workspace";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const maxUses = form.maxUses.trim() ? Number(form.maxUses) : null;
    if (maxUses !== null && (!Number.isInteger(maxUses) || maxUses < 1)) {
      setError("Max uses must be a whole number of at least 1, or empty for no limit.");
      return;
    }
    try {
      setCreated(
        await create.mutateAsync({
          role_id: roleId,
          project_id: form.projectId || null,
          expires_in_days: form.days,
          max_uses: maxUses,
          requires_approval: form.approval,
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the code.");
    }
  };

  const copy = async (text: string, what: string) => {
    try {
      await navigator.clipboard.writeText(text);
      notify(`${what} copied.`, "success");
    } catch {
      notify(`Could not copy. Select the ${what.toLowerCase()} and copy it by hand.`, "error");
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 360px) 1fr", gap: 24 }}>
      <section className="card" style={{ padding: 20 }} aria-labelledby="new-code-title">
        <h2 id="new-code-title" style={{ marginTop: 0, fontSize: 18 }}>
          New join code
        </h2>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <form onSubmit={submit}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="field">
              <label htmlFor="code-access">Gives access to</label>
              <select
                id="code-access"
                className="select"
                value={form.projectId}
                onChange={(event) => setForm({ ...form, projectId: event.target.value })}
              >
                <option value="">Whole workspace</option>
                {projects.data?.items.map((project) => (
                  <option key={project.id} value={project.id}>
                    Project: {project.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="code-role">Role</label>
              <select
                id="code-role"
                className="select"
                value={roleId}
                onChange={(event) => setForm({ ...form, roleId: event.target.value })}
              >
                {grantable.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="field-hint" style={{ marginTop: -8 }}>
            Codes can never give Owner or Admin.
          </p>
          <fieldset className="field" style={{ border: "none", padding: 0 }}>
            <legend>Expires after</legend>
            <div className="pill-group">
              {([1, 7, 30] as const).map((days) => (
                <label key={days} className="pill" style={{ cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="code-days"
                    checked={form.days === days}
                    onChange={() => setForm({ ...form, days })}
                  />{" "}
                  {days} {days === 1 ? "day" : "days"}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label htmlFor="code-max">Max uses</label>
            <input
              id="code-max"
              className="input"
              inputMode="numeric"
              value={form.maxUses}
              onChange={(event) => setForm({ ...form, maxUses: event.target.value })}
              style={{ maxWidth: 140 }}
            />
            <span className="field-hint">Leave empty for no limit until it expires.</span>
          </div>
          <label style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <input
              type="checkbox"
              checked={form.approval}
              onChange={(event) => setForm({ ...form, approval: event.target.checked })}
            />
            Approve each person before they join
          </label>
          <Button type="submit" variant="primary" loading={create.isPending} disabled={!roleId}>
            Create code
          </Button>
        </form>

        {created && (
          <div
            className="card"
            style={{ marginTop: 20, padding: 16, borderStyle: "dashed" }}
            role="status"
          >
            <div className="eyebrow">New code · shown only now</div>
            <p className="mono" style={{ fontSize: 28, letterSpacing: "0.08em", margin: "8px 0" }}>
              {created.code}
            </p>
            <div style={{ display: "flex", gap: 8 }}>
              <Button size="sm" onClick={() => copy(created.code, "Code")}>
                Copy code
              </Button>
              <Button size="sm" onClick={() => copy(joinLink(created.code), "Link")}>
                Copy link
              </Button>
            </div>
          </div>
        )}
      </section>

      <div style={{ display: "grid", gap: 24, alignContent: "start" }}>
        <JoinRequestsTab workspaceId={workspaceId} roles={grantable} />
        <section className="card" style={{ overflowX: "auto" }} aria-label="Join codes">
          {codes.data && codes.data.length === 0 ? (
            <p className="empty-state">No join codes yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Access</th>
                  <th scope="col">Role</th>
                  <th scope="col">Used</th>
                  <th scope="col">Expires</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {codes.data?.map((code) => (
                  <tr key={code.id}>
                    <td className="mono">…{code.code_hint}</td>
                    <td>{projectName(code.project_id)}</td>
                    <td>
                      {code.role.name}
                      {code.requires_approval && (
                        <>
                          {" "}
                          <Badge tone="info">approval</Badge>
                        </>
                      )}
                    </td>
                    <td className="mono">
                      {code.uses} / {code.max_uses ?? "∞"}
                    </td>
                    <td className="mono">
                      {code.status === "active"
                        ? dateFormat.format(new Date(code.expires_at))
                        : STATUS_TEXT[code.status]}
                    </td>
                    <td>
                      {code.status === "active" && (
                        <Button
                          size="sm"
                          onClick={() => revoke.mutate(code.id)}
                          aria-label={`Revoke code ending ${code.code_hint}`}
                        >
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
