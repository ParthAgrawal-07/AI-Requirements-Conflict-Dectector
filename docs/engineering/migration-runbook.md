# Migration runbook — rehearse on a copy of real data first

Some migrations rewrite data, not just structure. **`0004_tenancy_roles`** moves users from "one workspace and one role
each" to projects, memberships and roles: it backfills rows and drops two columns. Rehearse it on a copy of the real
database before it reaches Render. The same steps apply to any later data-changing migration.

> The container entrypoint runs `alembic upgrade head` **every time the API starts**. A branch or preview deploy that
> points at the *shared* database therefore migrates it for everyone — and an older deploy then fails with
> `Can't locate revision identified by '0004'`. Give previews their own database, or do not deploy the branch until the
> migration has been rehearsed and merged.

## 1. Copy the production data (read-only on production)

```bash
# Render dashboard → your Postgres → "External Database URL"
pg_dump --no-owner --no-acl --format=custom "<EXTERNAL_DATABASE_URL>" -f prod.dump
```

(No local `pg_dump`? Run it in a container: `docker run --rm -v "$PWD:/out" postgres:16 pg_dump … -f /out/prod.dump`.)

## 2. Restore it into a scratch database

```bash
createdb rcd_rehearsal
pg_restore --no-owner --no-acl -d rcd_rehearsal prod.dump
```

The scratch database needs the `vector` extension (pgvector) like production; use the `pgvector/pgvector` image if your
local Postgres lacks it.

## 3. Record "before", migrate, record "after"

```bash
psql rcd_rehearsal -c "select 'workspaces',count(*) from workspaces union all select 'users',count(*) from users
                       union all select 'documents',count(*) from documents union all select 'requirements',count(*) from requirements"
cd backend
DATABASE_URL=postgresql://localhost/rcd_rehearsal alembic upgrade head      # time it; read any error
psql rcd_rehearsal -c "<the same query>"                                    # counts must be identical
```

## 4. Run the verification script

```bash
psql rcd_rehearsal -f backend/scripts/verify_tenancy_backfill.sql
```

Every row must show `problems = 0`. It checks that every workspace has a project, every document and requirement
points at a project of its own workspace, every workspace with members has exactly one Owner, nobody lost their
membership, the nine default roles exist, and no `critical` severity is left. (`tests/db/test_tenancy_migrations.py`
runs the same script on a generated 18,000-requirement dataset and on deliberately broken data, so it is known to
detect problems.)

## 5. Also check the downgrade path

```bash
DATABASE_URL=postgresql://localhost/rcd_rehearsal alembic downgrade 0003
DATABASE_URL=postgresql://localhost/rcd_rehearsal alembic upgrade head
```

Downgrading is best-effort (an Owner becomes `admin`, custom roles become `analyst`, platform admins and service
accounts are parked in a "Recovered users" workspace) — it is for emergencies, not routine use.

## 6. Deploying

1. Take a Render database backup/snapshot first.
2. Deploy to **one** service (the API runs the migration; the worker runs with `RUN_MIGRATIONS=0`).
3. If the deploy fails, the **first traceback in the deploy log** decides what happened:

| Log says | Meaning | Fix |
|---|---|---|
| `Can't locate revision identified by '0004'` | a branch already migrated the shared DB; this code does not know the revision | deploy the branch that has `0004`, or restore the snapshot |
| `Multiple head revisions are present` | two migrations share a parent (for example another teammate's `0005` and `0011` both on `0004`) | give one of them the other as `down_revision` |
| `relation "projects" already exists` / `column … already exists` | a previous attempt or another branch partly applied it | restore the snapshot; do not edit applied migrations |
| a SQL error inside `0004` (`null value in column`, `violates … constraint`) | real data has a shape the backfill did not expect | rehearse on a copy (above) and fix the data or the migration |
| `ModuleNotFoundError` / `ImportError` at start | a dependency missing from `requirements.txt` | add it and rebuild |
| the API starts but `/health/ready` fails | database or Redis URL/credentials | check the service's environment variables |
