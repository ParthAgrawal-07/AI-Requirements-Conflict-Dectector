# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in the AI Requirements Conflict Detector, please
report it responsibly:

1. **Do not** open a public issue.
2. Email the maintainers directly with a description of the vulnerability, steps to reproduce,
   and any potential impact.
3. We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for
   critical issues.

## Security Measures

This project implements several security measures:

- **Authentication**: JWT-based auth with refresh token rotation (US-19). Tokens are signed with
  a strong secret enforced at startup in staging/production.
- **Authorization**: Permission-based access control (ADR-20) — routes check permission names,
  never role names, so the role→permission mapping can evolve without code changes.
- **Input validation**: All uploads are validated by extension, magic bytes, and structural
  integrity before processing (FR-02). Filenames are sanitized; client-supplied `Content-Type`
  is never trusted.
- **Rate limiting**: Sign-up, join-code redemption, and authoring endpoints are rate-limited per
  IP and per user to prevent brute-force attacks (NFR-35).
- **CSRF protection**: The refresh endpoint requires a custom `X-Requested-With` header, forcing
  a CORS preflight that prevents cross-site form posts.
- **CORS**: Explicit origin lists are enforced in staging/production; wildcard `*` is rejected.
- **Secrets**: `JWT_SECRET` and `JOIN_CODE_PEPPER` must meet a minimum length in staging/production;
  dev-only placeholder prefixes are rejected.
- **SQL injection**: All database queries go through SQLAlchemy ORM with parameterized queries.
- **Upload safety**: DOCX files are checked for zip-bomb characteristics (entry count and
  uncompressed size limits). PDF end-of-file markers are verified.
- **No credential echoing**: Validation error responses never echo submitted values back.
- **Audit trail**: Every finding, override, and sign-off is logged (FR-20).

## Environment Variables

See [`.env.example`](.env.example) for the full list. In production:

- Generate `JWT_SECRET` with: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- Generate `JOIN_CODE_PEPPER` similarly
- Set `CORS_ALLOWED_ORIGINS` to your explicit frontend domain(s)
- Set `TRUSTED_PROXY_HOPS` to match your reverse proxy depth
