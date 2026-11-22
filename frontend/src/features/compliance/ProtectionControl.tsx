import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useSetProtection } from "./api";

export interface ProtectionControlProps {
  projectId: string;
  requirementId: string;
  label: string | null;
  isProtected: boolean;
}

/** Mark a requirement compliance-critical, or remove the mark with a reason (Abhijeet — US-18;
 *  ``req.protect``). Both are audited on the server; removing it never happens silently. */
export function ProtectionControl({ projectId, requirementId, label, isProtected }: ProtectionControlProps) {
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const update = useSetProtection(projectId, requirementId);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  if (!can("req.protect")) return null;

  const name = label ?? "The requirement";
  const fail = (error: unknown) => notify(error instanceof ApiError ? error.message : "Could not change it", "error");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const why = reason.trim();
    if (isProtected && !why) return;
    update.mutate(
      { protected: !isProtected, reason: why || undefined },
      {
        onSuccess: () => {
          notify(isProtected ? `${name} is no longer protected` : `${name} is now protected`, "success");
          setOpen(false);
          setReason("");
        },
        onError: fail,
      },
    );
  };

  return (
    <div className="protection-control">
      <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
        {isProtected ? "Remove protection…" : "Mark protected…"}
      </Button>
      {open && (
        <form className="form-stack" onSubmit={submit} aria-label={isProtected ? "Remove protection" : "Mark protected"}>
          <label>
            {isProtected ? "Why remove it? (required, recorded)" : "Why is it compliance-critical? (optional, recorded)"}
            <textarea rows={2} maxLength={1000} required={isProtected} value={reason}
              onChange={(event) => setReason(event.target.value)} />
          </label>
          <p className="muted small">
            {isProtected
              ? "Changes and findings on it will no longer need a compliance reviewer."
              : "From now on only a compliance reviewer can decide its findings and approve its changes."}
          </p>
          <div className="row-actions">
            <Button type="submit" size="sm" variant={isProtected ? "secondary" : "primary"} loading={update.isPending}
              disabled={isProtected && !reason.trim()}>
              {isProtected ? "Remove protection" : "Protect"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
