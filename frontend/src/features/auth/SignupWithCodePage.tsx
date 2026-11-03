import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { Button } from "../../components/Button";
import { AuthLayout, AuthSwitch } from "./AuthLayout";

/**
 * Sign up with a join code (US-19, US-25). There is no open sign-up: the account is created only
 * together with a valid code. The API answers a bad code and an already-registered e-mail with
 * the same message on purpose, so this screen shows that message as it is.
 * A link like /signup?code=K7QM-4XPA fills the code in.
 */
export function SignupWithCodePage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({
    code: params.get("code") ?? "",
    full_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);

  const update = (name: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [name]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setBusy(true);
    try {
      const result = await signup({ ...form, email: form.email.trim(), code: form.code.trim() });
      if (result.join_status === "pending_approval") {
        setPending(true);
      } else {
        navigate(result.workspace_id ? `/w/${result.workspace_id}` : "/", { replace: true });
      }
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFieldErrors(caught.fieldErrors);
      } else {
        setError("Sign-up failed. Try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  if (pending) {
    return (
      <AuthLayout>
        <h1>Request sent</h1>
        <p role="status">
          Your account is ready. A project manager has to approve your request before you can see
          the workspace — you will find it here once they do.
        </p>
        <Link to="/" className="btn btn-primary">
          Continue
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h1>Join your team</h1>
      <p className="muted">Enter the code your project manager shared, then create your account.</p>
      <AuthSwitch />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={submit} noValidate>
        <Field id="signup-code" label="Join code" error={fieldErrors.code}>
          <input
            id="signup-code"
            className="input mono"
            placeholder="K7QM-4XPA"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            required
            value={form.code}
            onChange={(event) => update("code")(event.target.value)}
          />
        </Field>
        <Field id="signup-name" label="Full name" error={fieldErrors.full_name}>
          <input
            id="signup-name"
            className="input"
            autoComplete="name"
            required
            value={form.full_name}
            onChange={(event) => update("full_name")(event.target.value)}
          />
        </Field>
        <Field id="signup-email" label="Work email" error={fieldErrors.email}>
          <input
            id="signup-email"
            className="input"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(event) => update("email")(event.target.value)}
          />
        </Field>
        <Field
          id="signup-password"
          label="Password"
          hint="At least 12 characters."
          error={fieldErrors.password}
        >
          <input
            id="signup-password"
            className="input"
            type="password"
            autoComplete="new-password"
            required
            value={form.password}
            onChange={(event) => update("password")(event.target.value)}
          />
        </Field>
        <Button type="submit" variant="primary" className="btn-block" loading={busy}>
          Create account and join
        </Button>
      </form>
      <p className="muted" style={{ marginTop: 24 }}>
        Already have an account? <Link to="/login">Sign in</Link> and enter the code there.
      </p>
    </AuthLayout>
  );
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
