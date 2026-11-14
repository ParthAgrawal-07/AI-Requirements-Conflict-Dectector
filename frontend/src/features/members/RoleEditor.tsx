import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { usePermissionCatalogue, type PermissionInfo, type RoleInput, type RoleRead } from "./api";

const GROUPS: PermissionInfo["group"][] = ["Workspace", "Requirements", "Review", "Governance"];

// The actions people ask about first, in the words of the role page (interface design §4.3).
const PHRASES: [permission: string, phrase: string][] = [
  ["req.propose", "propose requirements"],
  ["message.post", "post in channels"],
  ["req.comment", "comment"],
  ["rcr.review", "review change requests"],
  ["rcr.merge", "merge"],
  ["finding.review", "review findings"],
  ["members.manage", "manage members"],
  ["channel.manage", "manage channels"],
  ["baseline.manage", "manage the baseline"],
];

/** One sentence saying what a role can and cannot do, e.g. "This role can review change
 *  requests and comment, but not propose requirements or merge." */
export function describeRole(permissions: Iterable<string>): string {
  const held = new Set(permissions);
  const can = PHRASES.filter(([p]) => held.has(p)).map(([, phrase]) => phrase);
  const cannot = PHRASES.filter(([p]) => !held.has(p)).map(([, phrase]) => phrase).slice(0, 3);
  const list = (items: string[], joiner: string) =>
    items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} ${joiner} ${items[items.length - 1]}`;
  if (held.size === 0) return "This role can do nothing yet: tick at least one permission.";
  const first = can.length ? `This role can ${list(can, "and")}` : held.has("view") ? "This role can only read" : "This role can";
  return cannot.length ? `${first}, but not ${list(cannot, "or")}.` : `${first}.`;
}

export interface RoleEditorProps {
  open: boolean;
  role: RoleRead | null; // null: a new custom role
  heldByMe: Set<string>; // nobody can grant what they do not hold (enforced by the server too)
  onSave: (input: RoleInput) => Promise<unknown>;
  onClose: () => void;
}

/** Create or edit a custom role (US-49): a permission checklist grouped by area. */
export function RoleEditor({ open, role, heldByMe, onSave, onClose }: RoleEditorProps) {
  const catalogue = usePermissionCatalogue();
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? ["view"]));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function toggle(permission: string) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(permission)) next.delete(permission);
      else next.add(permission);
      return next;
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSave({ name: name.trim(), description: description.trim() || null, permissions: [...chosen].sort() });
      onClose();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "The role could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer open={open} title={role ? `Edit ${role.name}` : "New custom role"} onClose={onClose}>
      <form className="form-stack" onSubmit={submit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} placeholder="Client reviewer" />
        </label>
        <label>
          Description (optional)
          <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} />
        </label>
        <p className="role-sentence" aria-live="polite">
          {describeRole(chosen)}
        </p>
        {catalogue.isError && <p role="alert">The permission list could not be loaded.</p>}
        {GROUPS.map((group) => {
          const items = (catalogue.data ?? []).filter((p) => p.group === group && p.name !== "workspace.manage");
          if (items.length === 0) return null;
          return (
            <fieldset key={group} className="permission-group">
              <legend>{group}</legend>
              {items.map((permission) => {
                const grantable = heldByMe.has(permission.name) || chosen.has(permission.name);
                return (
                  <label key={permission.name} className="checkbox">
                    <input
                      type="checkbox"
                      checked={chosen.has(permission.name)}
                      disabled={!grantable}
                      onChange={() => toggle(permission.name)}
                    />
                    <span>
                      {permission.description} <span className="mono muted small">{permission.name}</span>
                      {!grantable && <span className="muted small"> — you do not hold it</span>}
                    </span>
                  </label>
                );
              })}
            </fieldset>
          );
        })}
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={saving} disabled={!name.trim() || chosen.size === 0}>
          {role ? "Save role" : "Create role"}
        </Button>
      </form>
    </Drawer>
  );
}
