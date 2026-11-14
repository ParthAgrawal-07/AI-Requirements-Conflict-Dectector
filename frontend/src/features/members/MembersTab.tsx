import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/Toast";
import { useProjects } from "../projects/api";
import {
  useChangeRole,
  useLeaveWorkspace,
  useMembers,
  useNeedsReassignment,
  useProjectMembers,
  useRemoveMember,
  useRoles,
  useSetProjectRole,
  type Member,
  type RoleRead,
} from "./api";

function failure(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** Members (US-26; interface design §4.3): role editable inline by those with members.manage,
 *  Remove, project-level roles, and Leave for yourself. Access ends on the member's next request
 *  and their open sockets close. */
export function MembersTab({ workspaceId }: { workspaceId: string }) {
  const { user } = useAuth();
  const members = useMembers(workspaceId);
  const roles = useRoles(workspaceId);
  const { can } = usePermissions({ workspaceId });
  const manage = can("members.manage");
  const changeRole = useChangeRole(workspaceId);
  const remove = useRemoveMember(workspaceId);
  const leave = useLeaveWorkspace(workspaceId);
  const orphans = useNeedsReassignment(workspaceId, manage);
  const toast = useToast();
  const navigate = useNavigate();
  const [projectRoles, setProjectRoles] = useState<Member | null>(null);

  return (
    <div>
      <table className="table">
        <caption className="sr-only">Workspace members</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Role</th>
            <th scope="col">Joined</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {members.data?.map((member) => {
            const self = member.user.id === user?.id;
            return (
              <tr key={member.user.id}>
                <td>
                  {member.user.full_name}
                  {self && <span className="muted"> (you)</span>}
                  <div className="muted small">{member.user.email}</div>
                </td>
                <td>
                  {manage ? (
                    <select
                      aria-label={`Role of ${member.user.full_name}`}
                      value={member.role.id}
                      onChange={(event) =>
                        changeRole.mutate(
                          { userId: member.user.id, roleId: event.target.value },
                          {
                            onSuccess: () => toast(`${member.user.full_name} is now ${roleName(roles.data, event.target.value)}.`, "success"),
                            onError: (error) => toast(failure(error, "The role could not be changed."), "error"),
                          },
                        )
                      }
                    >
                      {roles.data?.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    member.role.name
                  )}
                </td>
                <td>{new Date(member.joined_at).toLocaleDateString()}</td>
                <td className="row-actions">
                  {manage && (
                    <Button size="sm" variant="ghost" onClick={() => setProjectRoles(member)}>
                      Project roles
                    </Button>
                  )}
                  {manage && !self && (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        if (!window.confirm(`Remove ${member.user.full_name}? Their messages and decisions stay.`)) return;
                        remove.mutate(member.user.id, {
                          onError: (error) => toast(failure(error, "The member could not be removed."), "error"),
                        });
                      }}
                    >
                      Remove
                    </Button>
                  )}
                  {self && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        if (!window.confirm("Leave this workspace? You will need a new code to come back.")) return;
                        leave.mutate(undefined, {
                          onSuccess: () => navigate("/"),
                          onError: (error) => toast(failure(error, "You could not leave."), "error"),
                        });
                      }}
                    >
                      Leave workspace
                    </Button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {manage && (orphans.data?.length ?? 0) > 0 && (
        <section className="card reassign" aria-labelledby="reassign-title">
          <h2 id="reassign-title">Needs reassignment</h2>
          <p className="muted">Requirements still owned by people who left. Give them a new owner.</p>
          <ul>
            {orphans.data?.map((item) => (
              <li key={item.id}>
                <span className="mono">{item.label ?? "Unnumbered requirement"}</span> — owned by{" "}
                {item.former_owner_name} <span className="muted">(former member)</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {projectRoles && (
        <ProjectRoles
          workspaceId={workspaceId}
          member={projectRoles}
          roles={roles.data ?? []}
          onClose={() => setProjectRoles(null)}
        />
      )}
    </div>
  );
}

function roleName(roles: RoleRead[] | undefined, id: string): string {
  return roles?.find((role) => role.id === id)?.name ?? "updated";
}

/** A member's role inside each project (US-49, FR-79). Never more than you may give out. */
function ProjectRoles({
  workspaceId,
  member,
  roles,
  onClose,
}: {
  workspaceId: string;
  member: Member;
  roles: RoleRead[];
  onClose: () => void;
}) {
  const projects = useProjects(workspaceId);
  return (
    <Drawer open title={`${member.user.full_name} in each project`} onClose={onClose}>
      <p className="muted">
        A project role replaces the workspace role ({member.role.name}) inside that project only.
      </p>
      {projects.data?.items.map((project) => (
        <ProjectRoleRow key={project.id} projectId={project.id} projectName={project.name} member={member} roles={roles} />
      ))}
    </Drawer>
  );
}

function ProjectRoleRow({
  projectId,
  projectName,
  member,
  roles,
}: {
  projectId: string;
  projectName: string;
  member: Member;
  roles: RoleRead[];
}) {
  const team = useProjectMembers(projectId);
  const set = useSetProjectRole(projectId);
  const toast = useToast();
  const current = team.data?.find((entry) => entry.user_id === member.user.id)?.role_override?.id ?? "";
  // Ownership is never per project (the server refuses it as well).
  const choices = roles.filter((role) => !role.permissions.includes("workspace.manage"));
  return (
    <label className="project-role">
      {projectName}
      <select
        value={current}
        onChange={(event) =>
          set.mutate(
            { userId: member.user.id, roleId: event.target.value || null },
            { onError: (error) => toast(failure(error, "The project role could not be set."), "error") },
          )
        }
      >
        <option value="">Workspace role ({member.role.name})</option>
        {choices.map((role) => (
          <option key={role.id} value={role.id}>
            {role.name}
          </option>
        ))}
      </select>
    </label>
  );
}
