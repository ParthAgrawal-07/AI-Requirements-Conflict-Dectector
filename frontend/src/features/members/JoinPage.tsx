import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { Button } from "../../components/Button";
import { AuthLayout } from "../auth/AuthLayout";
import { useJoinWithCode } from "./api";

/**
 * Join with a code or a link (US-25). A join link /join/K7QM-4XPA sends a signed-out visitor to
 * sign-up with the code filled in; a signed-in member enters or confirms the code here.
 */
export function JoinPage() {
  const { code: linkCode = "" } = useParams();
  const { token } = useAuth();
  const navigate = useNavigate();
  const join = useJoinWithCode();
  const [code, setCode] = useState(linkCode);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!token) {
    return <Navigate to={`/signup${linkCode ? `?code=${encodeURIComponent(linkCode)}` : ""}`} replace />;
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await join.mutateAsync(code.trim());
      if (result.status === "pending_approval") {
        setPending(true);
      } else {
        navigate(
          result.project_id
            ? `/w/${result.workspace_id}/p/${result.project_id}`
            : `/w/${result.workspace_id}`,
          { replace: true },
        );
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not join. Try again.");
    }
  };

  return (
    <AuthLayout>
      <h1>{pending ? "Request sent" : "Join with a code"}</h1>
      {pending ? (
        <p role="status">A project manager will approve your request. You can close this page.</p>
      ) : (
        <form onSubmit={submit}>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="field">
            <label htmlFor="join-code">Join code</label>
            <input
              id="join-code"
              className="input mono"
              placeholder="K7QM-4XPA"
              autoComplete="off"
              spellCheck={false}
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </div>
          <Button type="submit" variant="primary" className="btn-block" loading={join.isPending}>
            Join
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
