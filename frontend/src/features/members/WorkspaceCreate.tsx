import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { useCreateWorkspace } from "./api";

/** Create a workspace (US-24). The creator becomes its Owner. Who may create one is the
 *  server's decision (platform admins, or everyone when the deployment allows it). */
export function WorkspaceCreate() {
  const navigate = useNavigate();
  const create = useCreateWorkspace();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const workspace = await create.mutateAsync(name.trim());
      navigate(`/w/${workspace.id}/projects/new`, { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the workspace.");
    }
  };

  return (
    <div className="page" style={{ maxWidth: 560 }}>
      <h1>Create a workspace</h1>
      <p className="muted">
        A workspace holds your team and its projects. You become its Owner; next you create the
        first project.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="workspace-name">Workspace name</label>
          <input
            id="workspace-name"
            className="input"
            maxLength={120}
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <Button type="submit" variant="primary" loading={create.isPending} disabled={!name.trim()}>
          Create workspace
        </Button>
      </form>
    </div>
  );
}
