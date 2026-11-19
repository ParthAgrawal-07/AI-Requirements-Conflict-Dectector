import { Link, useParams } from "react-router-dom";
import { WordDiff } from "../../components/WordDiff";
import { useVersions } from "./api";

export interface VersionHistoryProps {
  requirementId: string;
}

function when(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

/** Every version of a requirement, newest first (US-12): who changed it, from which change
 *  request, and what changed against the version before, word by word. */
export function VersionHistory({ requirementId }: VersionHistoryProps) {
  const { workspaceId, projectId } = useParams();
  const versions = useVersions(requirementId);
  if (versions.isLoading) return <p className="muted">Loading history…</p>;
  if (versions.isError) return <p role="alert">The history could not be loaded.</p>;
  const rows = versions.data ?? [];
  if (rows.length === 0) return <p className="muted small">No versions recorded yet.</p>;
  return (
    <ol className="version-list" aria-label="Versions">
      {rows.map((version, index) => {
        const older = rows[index + 1];
        return (
          <li key={version.version_no} className="version">
            <p className="version-meta">
              <strong>v{version.version_no}</strong>
              <span className="muted small">
                {" · "}
                {version.changed_by ? version.changed_by.full_name : "From the document"}
                {" · "}
                <time dateTime={version.changed_at}>{when(version.changed_at)}</time>
              </span>
              {version.change_request && workspaceId && projectId && (
                <>
                  {" · "}
                  <Link to={`/w/${workspaceId}/p/${projectId}/changes/${version.change_request.id}`}>
                    {version.change_request.key}
                  </Link>
                </>
              )}
            </p>
            {older ? (
              <WordDiff before={older.body} after={version.body} label={`Changes from v${older.version_no}`} />
            ) : (
              <p className="requirement-quote">{version.body}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
