import { useState } from "react";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import {
  useCreateRole,
  useDeleteRole,
  usePermissionCatalogue,
  useRoles,
  useUpdateRole,
  type RoleRead,
} from "./api";
import { describeRole, RoleEditor } from "./RoleEditor";

/** Roles (US-27, US-49): the nine default roles, read-only, and the workspace's custom roles,
 *  which Owners and Admins create, edit and delete. */
export function RolesTab({ workspaceId }: { workspaceId: string }) {
  const roles = useRoles(workspaceId);
  const catalogue = usePermissionCatalogue();
  const { can } = usePermissions({ workspaceId });
  const create = useCreateRole(workspaceId);
  const update = useUpdateRole(workspaceId);
  const remove = useDeleteRole(workspaceId);
  const toast = useToast();
  const [editing, setEditing] = useState<RoleRead | "new" | null>(null);
  const manage = can("roles.manage");
  const heldByMe = new Set((catalogue.data ?? []).map((p) => p.name).filter((name) => can(name)));

  return (
    <div>
      {manage && (
        <div className="page-header">
          <p className="muted" style={{ margin: 0 }}>
            Default roles cannot be changed. A custom role holds only permissions you hold yourself.
          </p>
          <Button variant="primary" onClick={() => setEditing("new")}>
            + Custom role
          </Button>
        </div>
      )}
      <ul className="role-list">
        {roles.data?.map((role) => (
          <li key={role.id} className="card role-card">
            <strong>{role.name}</strong>{" "}
            {role.is_default ? <Badge>default</Badge> : <Badge tone="info">custom</Badge>}{" "}
            {!role.grantable_by_join_code && <Badge tone="neutral">not by join code</Badge>}
            {role.description && <p className="muted">{role.description}</p>}
            <p className="role-sentence">{describeRole(role.permissions)}</p>
            <details>
              <summary>{role.permissions.length} permissions</summary>
              <p className="mono small">{role.permissions.join(" · ")}</p>
            </details>
            {manage && !role.is_default && (
              <div className="role-actions">
                <Button size="sm" onClick={() => setEditing(role)}>
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => {
                    if (!window.confirm(`Delete the role “${role.name}”?`)) return;
                    remove.mutate(role.id, {
                      onError: (error) =>
                        toast(error instanceof ApiError ? error.message : "The role could not be deleted.", "error"),
                    });
                  }}
                >
                  Delete
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {editing !== null && (
        <RoleEditor
          key={editing === "new" ? "new" : editing.id}
          open
          role={editing === "new" ? null : editing}
          heldByMe={heldByMe}
          onClose={() => setEditing(null)}
          onSave={(input) =>
            editing === "new" ? create.mutateAsync(input) : update.mutateAsync({ id: editing.id, ...input })
          }
        />
      )}
    </div>
  );
}
