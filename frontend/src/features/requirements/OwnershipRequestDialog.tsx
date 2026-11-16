import { useState } from "react";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/Toast";
import { useDecideOwnership, useOwnershipRequests, useRequestOwnership } from "./api";
import { OwnerChip } from "./OwnerChip";

export interface OwnershipRequestDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  requirement: {
    requirement_id: string;
    source_req_id: string | null;
    owner_id: string | null;
    owner_name: string | null;
    stakeholder_group: string | null;
  };
  /** May the caller ask (``req.propose``) and may it decide for anyone (``baseline.manage``)? */
  canRequest: boolean;
  canManage: boolean;
  names: Map<string, string>;
}

/** Ask to own a requirement, and — for its owner or a manager — decide the pending requests
 *  (US-36). The server enforces both; this only hides what the member cannot do. */
export function OwnershipRequestDialog({
  open,
  onClose,
  projectId,
  requirement,
  canRequest,
  canManage,
  names,
}: OwnershipRequestDialogProps) {
  const { user } = useAuth();
  const notify = useToast();
  const [note, setNote] = useState("");
  const id = requirement.requirement_id;
  const requests = useOwnershipRequests(id, open);
  const ask = useRequestOwnership(id);
  const decide = useDecideOwnership(id, projectId);
  const isOwner = requirement.owner_id !== null && requirement.owner_id === user?.id;
  const mayDecide = isOwner || canManage;
  const pending = (requests.data ?? []).filter((r) => r.status === "pending");
  const mine = pending.some((r) => r.requester_id === user?.id);
  const label = requirement.source_req_id ?? "this requirement";

  const fail = (error: unknown) =>
    notify(error instanceof ApiError ? error.message : "Something went wrong", "error");

  return (
    <Drawer open={open} onClose={onClose} title={`Ownership of ${label}`}>
      <p>
        <OwnerChip ownerName={requirement.owner_name} group={requirement.stakeholder_group} />
      </p>

      {canRequest && !isOwner && !mine && (
        <form
          className="form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            ask.mutate(note, {
              onSuccess: () => {
                notify(`You asked to own ${label}`, "success");
                setNote("");
              },
              onError: fail,
            });
          }}
        >
          <label>
            Why should you own it? <span className="muted small">(optional)</span>
            <textarea
              rows={2}
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <Button type="submit" variant="primary" loading={ask.isPending}>
            Request ownership
          </Button>
        </form>
      )}
      {mine && <p className="muted">Your request is waiting for the owner or a manager.</p>}

      {pending.length > 0 && (
        <section aria-label="Pending requests">
          <h3>Pending requests</h3>
          <ul className="plain-list">
            {pending.map((request) => (
              <li key={request.id}>
                <strong>{names.get(request.requester_id) ?? "A member"}</strong>
                {request.note && <span className="muted"> — {request.note}</span>}
                {mayDecide && (
                  <span className="row-actions">
                    <Button
                      size="sm"
                      variant="primary"
                      loading={decide.isPending}
                      onClick={() =>
                        decide.mutate({ requestId: request.id, accept: true }, { onError: fail })
                      }
                    >
                      Accept
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        decide.mutate({ requestId: request.id, accept: false }, { onError: fail })
                      }
                    >
                      Decline
                    </Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Drawer>
  );
}
