import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useMembers } from "../channels/api";
import { useRoles } from "./api";
import {
  describeMatch,
  useCreateRule,
  useDecisionRules,
  useDeleteRule,
  type OwnerKind,
  type RuleInput,
} from "./decisionRules";

type MatchField = "match_protected" | "match_category" | "match_label" | "match_group" | "match_req_type";

const MATCH_FIELDS: { value: MatchField; label: string }[] = [
  { value: "match_protected", label: "Protected requirement" },
  { value: "match_category", label: "Finding category" },
  { value: "match_label", label: "Issue label" },
  { value: "match_group", label: "Stakeholder group" },
  { value: "match_req_type", label: "Requirement type" },
];

/** Decision rules (US-57, interface design §8b): match → decision owner → required reviewers,
 *  most specific first, the default rule pinned at the bottom. Managers edit; everyone reads.
 *  Edits apply to open items at their next update. */
export function DecisionRulesTab({ workspaceId, projectId }: { workspaceId: string; projectId: string }) {
  const { can } = usePermissions({ projectId });
  const rules = useDecisionRules(projectId);
  const remove = useDeleteRule(projectId);
  const notify = useToast();
  const manage = can("project.manage");

  return (
    <section aria-label="Decision rules">
      <p className="muted">
        Who decides which kind of question. Approval counts and votes never replace the decision
        owner.
      </p>
      {rules.isLoading && <p className="muted">Loading…</p>}
      {rules.data && (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col">Matches</th>
              <th scope="col">Decides</th>
              <th scope="col">Required reviewers</th>
              {manage && <th scope="col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {rules.data.map((rule) => (
              <tr key={rule.id}>
                <td>
                  {rule.name} {rule.is_default && <Badge tone="info">Default</Badge>}
                </td>
                <td>{describeMatch(rule)}</td>
                <td>{rule.owner.name}</td>
                <td>{rule.required_reviewers.map((r) => r.name).join(", ") || "—"}</td>
                {manage && (
                  <td>
                    {!rule.is_default && (
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Delete rule ${rule.name}`}
                        onClick={() =>
                          remove.mutate(rule.id, {
                            onError: (error) =>
                              notify(error instanceof ApiError ? error.message : "Could not delete", "error"),
                          })
                        }
                      >
                        Delete
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {manage && <AddRule workspaceId={workspaceId} projectId={projectId} />}
    </section>
  );
}

function AddRule({ workspaceId, projectId }: { workspaceId: string; projectId: string }) {
  const create = useCreateRule(projectId);
  const roles = useRoles(workspaceId);
  const members = useMembers(workspaceId);
  const notify = useToast();
  const [name, setName] = useState("");
  const [field, setField] = useState<MatchField>("match_group");
  const [value, setValue] = useState("");
  const [ownerKind, setOwnerKind] = useState<OwnerKind>("role");
  const [ownerId, setOwnerId] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const input: RuleInput = {
      name: name.trim(),
      owner_kind: ownerKind,
      owner_id: ownerKind === "requirement_owner" ? null : ownerId || null,
      [field]: field === "match_protected" ? value !== "false" : value.trim(),
    };
    create.mutate(input, {
      onSuccess: () => {
        notify(`Rule ${input.name} added`, "success");
        setName("");
        setValue("");
      },
      onError: (error) => notify(error instanceof ApiError ? error.message : "Could not add the rule", "error"),
    });
  };

  const owners =
    ownerKind === "role"
      ? (roles.data ?? []).map((role) => ({ id: role.id, name: role.name }))
      : (members.data ?? []).map((member) => ({ id: member.user.id, name: member.user.full_name }));

  return (
    <form className="inline-form" onSubmit={submit} aria-label="Add a decision rule">
      <label>
        Name <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} />
      </label>
      <label>
        When{" "}
        <select value={field} onChange={(event) => setField(event.target.value as MatchField)}>
          {MATCH_FIELDS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {field === "match_protected" ? (
        <label>
          is{" "}
          <select value={value || "true"} onChange={(event) => setValue(event.target.value)}>
            <option value="true">yes</option>
            <option value="false">no</option>
          </select>
        </label>
      ) : (
        <label>
          is <input value={value} onChange={(event) => setValue(event.target.value)} required />
        </label>
      )}
      <label>
        Decides{" "}
        <select value={ownerKind} onChange={(event) => setOwnerKind(event.target.value as OwnerKind)}>
          <option value="role">a role</option>
          <option value="user">a person</option>
          <option value="requirement_owner">the requirement owner</option>
        </select>
      </label>
      {ownerKind !== "requirement_owner" && (
        <label>
          Who{" "}
          <select value={ownerId} onChange={(event) => setOwnerId(event.target.value)} required>
            <option value="">Choose…</option>
            {owners.map((owner) => (
              <option key={owner.id} value={owner.id}>
                {owner.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <Button variant="primary" type="submit" loading={create.isPending}>
        Add rule
      </Button>
    </form>
  );
}

