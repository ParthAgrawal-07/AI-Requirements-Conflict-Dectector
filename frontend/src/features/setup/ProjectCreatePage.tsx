import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { rememberLastProject } from "../projects/api";
import { useCreateProject } from "./api";

/** New project (US-24). It starts in Setup and opens the setup wizard straight away (US-60). */
export function ProjectCreatePage() {
  const { workspaceId = "" } = useParams();
  const navigate = useNavigate();
  const create = useCreateProject(workspaceId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const project = await create.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
      });
      rememberLastProject(workspaceId, project.id);
      navigate(`/w/${workspaceId}/p/${project.id}/setup`, { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the project.");
    }
  };

  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <h1>New project</h1>
      <p className="muted">
        Each project has its own requirements, baseline and settings. Next you give it its
        context — the analysis stays off until you do.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="project-name">Project name</label>
          <input
            id="project-name"
            className="input"
            maxLength={120}
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="project-description">Description (optional)</label>
          <textarea
            id="project-description"
            className="textarea"
            rows={3}
            maxLength={2000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <Button type="submit" variant="primary" loading={create.isPending} disabled={!name.trim()}>
          Create and set up
        </Button>
      </form>
    </div>
  );
}
