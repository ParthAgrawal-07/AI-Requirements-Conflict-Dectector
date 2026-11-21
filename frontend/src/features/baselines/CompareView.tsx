import { WordDiff } from "../../components/WordDiff";
import { useComparison } from "./api";

export interface CompareViewProps {
  base: string | null;
  target: string | null;
}

/** What changed from one snapshot to another (US-40): added, changed with a word diff, removed. */
export function CompareView({ base, target }: CompareViewProps) {
  const comparison = useComparison(base, target);
  if (!base || !target) return <p className="muted">Choose two baselines to compare.</p>;
  if (base === target) return <p className="muted">Choose two different baselines.</p>;
  if (comparison.isLoading) return <p className="muted">Comparing…</p>;
  if (comparison.isError || !comparison.data) return <p role="alert">The comparison could not be loaded.</p>;
  const { added, changed, removed, unchanged } = comparison.data;
  return (
    <section aria-label={`${comparison.data.base.label} compared with ${comparison.data.target.label}`}>
      <p>
        <strong>{added.length}</strong> added · <strong>{changed.length}</strong> changed ·{" "}
        <strong>{removed.length}</strong> removed · {unchanged} unchanged
      </p>

      <h2>Added</h2>
      {added.length === 0 ? (
        <p className="muted small">None</p>
      ) : (
        <ul className="compare-list">
          {added.map((entry) => (
            <li key={entry.requirement_id}>
              <span className="mono">+ {entry.label ?? "Unnumbered"}</span> v{entry.version} — {entry.body}
            </li>
          ))}
        </ul>
      )}

      <h2>Changed</h2>
      {changed.length === 0 ? (
        <p className="muted small">None</p>
      ) : (
        <ul className="compare-list">
          {changed.map((entry) => (
            <li key={entry.requirement_id}>
              <span className="mono">~ {entry.label ?? "Unnumbered"}</span> v{entry.from_version} → v
              {entry.to_version}
              <WordDiff before={entry.before} after={entry.after} label={`Changes to ${entry.label ?? "the requirement"}`} />
            </li>
          ))}
        </ul>
      )}

      <h2>Removed</h2>
      {removed.length === 0 ? (
        <p className="muted small">None</p>
      ) : (
        <ul className="compare-list">
          {removed.map((entry) => (
            <li key={entry.requirement_id}>
              <span className="mono">− {entry.label ?? "Unnumbered"}</span> v{entry.version}
              {entry.state ? ` (now ${entry.state.replace("_", " ")})` : ""} — <del>{entry.body}</del>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
