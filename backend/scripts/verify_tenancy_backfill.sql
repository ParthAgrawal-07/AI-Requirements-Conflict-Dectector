-- Verify migration 0004 (tenancy backfill) on a COPY of real data.
--
--   psql "$SCRATCH_DATABASE_URL" -f backend/scripts/verify_tenancy_backfill.sql
--
-- Run it right after `alembic upgrade head` on a restored copy of the production database
-- (see docs/engineering/migration-runbook.md). Every row must show problems = 0.
-- Accounts created *after* the upgrade (for example a sign-up that is still pending approval)
-- legitimately have no membership, so run this on the copy straight after upgrading.

SELECT 'workspace without a project' AS check_name, count(*) AS problems
FROM workspaces w
WHERE NOT EXISTS (SELECT 1 FROM projects p WHERE p.workspace_id = w.id)

UNION ALL
SELECT 'document without a project', count(*) FROM documents WHERE project_id IS NULL

UNION ALL
SELECT 'document whose project belongs to another workspace', count(*)
FROM documents d JOIN projects p ON p.id = d.project_id
WHERE p.workspace_id <> d.workspace_id

UNION ALL
SELECT 'requirement without a project', count(*) FROM requirements WHERE project_id IS NULL

UNION ALL
SELECT 'requirement whose project differs from its document''s project', count(*)
FROM requirements r JOIN documents d ON d.id = r.document_id
WHERE r.project_id <> d.project_id

UNION ALL
SELECT 'workspace with members but no Owner', count(*)
FROM workspaces w
WHERE EXISTS (SELECT 1 FROM memberships m WHERE m.workspace_id = w.id AND m.ended_at IS NULL)
  AND NOT EXISTS (
      SELECT 1 FROM memberships m JOIN roles r ON r.id = m.role_id
      WHERE m.workspace_id = w.id AND m.ended_at IS NULL AND r.is_default AND r.name = 'Owner')

UNION ALL
SELECT 'workspace with more than one Owner (backfill gives exactly one)', count(*)
FROM (
    SELECT m.workspace_id
    FROM memberships m JOIN roles r ON r.id = m.role_id
    WHERE m.ended_at IS NULL AND r.is_default AND r.name = 'Owner'
    GROUP BY m.workspace_id HAVING count(*) > 1
) AS many

UNION ALL
SELECT 'person without any membership (neither service nor platform admin)', count(*)
FROM users u
WHERE u.platform_role IS NULL
  AND NOT EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = u.id)

UNION ALL
SELECT 'default roles missing (expected 9)', abs(9 - count(*)) FROM roles WHERE is_default

UNION ALL
SELECT 'findings still using the retired severity "critical"', count(*)
FROM findings WHERE severity = 'critical'

ORDER BY 1;
