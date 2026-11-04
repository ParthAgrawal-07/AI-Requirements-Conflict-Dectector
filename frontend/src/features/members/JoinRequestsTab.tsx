import { useState } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useDecideJoinRequest, useJoinRequests, type RoleRead } from "./api";

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

function ago(iso: string, now: number = Date.now()): string {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60_000);
  if (Math.abs(minutes) < 60) return relative.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return relative.format(hours, "hour");
  return relative.format(Math.round(hours / 24), "day");
}

/** Join requests waiting for a manager (US-25): approve with a role, or deny. */
export function JoinRequestsTab({
  workspaceId,
  roles,
}: {
  workspaceId: string;
  roles: RoleRead[];
}) {
  const requests = useJoinRequests(workspaceId);
  const decide = useDecideJoinRequest(workspaceId);
  const notify = useToast();
  const [chosen, setChosen] = useState<Record<string, string>>({});

  const act = async (id: string, approve: boolean, name: string) => {
    try {
      await decide.mutateAsync({ id, approve, roleId: approve ? chosen[id] : undefined });
      notify(approve ? `${name} can now join.` : `${name}'s request was denied.`, "success");
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "Could not save the decision.", "error");
    }
  };

  const waiting = requests.data ?? [];
  return (
    <section className="card" aria-labelledby="requests-title">
      <h2 id="requests-title" style={{ margin: 0, padding: "16px 20px", fontSize: 18 }}>
        Join requests{" "}
        {waiting.length > 0 && (
          <span className="mono" style={{ color: "var(--conflict)", fontSize: 14 }}>
            {waiting.length} waiting
          </span>
        )}
      </h2>
      {waiting.length === 0 ? (
        <p className="empty-state" style={{ paddingTop: 0 }}>
          Nobody is waiting.
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {waiting.map((request) => (
            <li
              key={request.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "12px 20px",
                borderTop: "1px solid var(--line)",
              }}
            >
              <div style={{ flex: 1 }}>
                <strong>{request.user.full_name}</strong>{" "}
                <span className="muted">{request.user.email}</span>
                <div className="mono muted" style={{ fontSize: 13 }}>
                  {ago(request.created_at)}
                </div>
              </div>
              <label className="visually-hidden" htmlFor={`role-${request.id}`}>
                Role for {request.user.full_name}
              </label>
              <select
                id={`role-${request.id}`}
                className="select"
                value={chosen[request.id] ?? request.role.id}
                onChange={(event) => setChosen({ ...chosen, [request.id]: event.target.value })}
              >
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
              <Button
                variant="primary"
                size="sm"
                onClick={() => act(request.id, true, request.user.full_name)}
              >
                Approve
              </Button>
              <Button size="sm" onClick={() => act(request.id, false, request.user.full_name)}>
                Deny
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
