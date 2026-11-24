import type { RevisionPoint } from "./history";

export interface TimeSliderProps {
  points: RevisionPoint[];
  /** The chosen point's snapshot id; null = now (the live map). */
  value: string | null;
  onChange: (snapshotId: string | null, point: RevisionPoint) => void;
}

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "now";
}

/** The time slider (Pranshu — US-50, FR-85): baseline revisions and labelled baselines, oldest to
 *  now. A point in the past shows that map read-only; the Changes panel follows it. A native range
 *  input, so keyboard (arrows, Home, End) and screen readers work as they do everywhere. */
export function TimeSlider({ points, value, onChange }: TimeSliderProps) {
  if (points.length < 2) {
    return (
      <p className="muted small time-slider-empty">
        The time slider fills in as changes are merged into the baseline and baselines are frozen.
      </p>
    );
  }
  const index = Math.max(
    0,
    points.findIndex((p) => p.id === value),
  );
  const current = value === null ? points.length - 1 : index;
  const point = points[current];
  return (
    <div className="time-slider">
      <label htmlFor="map-time" className="small">
        Map at
      </label>
      <input
        id="map-time"
        type="range"
        min={0}
        max={points.length - 1}
        step={1}
        value={current}
        aria-valuetext={`${point.label}, ${when(point.at)}`}
        onChange={(event) => {
          const next = points[Number(event.target.value)];
          onChange(next.id, next);
        }}
      />
      <ol className="time-ticks" aria-hidden="true">
        {points.map((p) => (
          <li key={p.id ?? "now"} className={p.kind === "baseline" ? "tick-baseline" : ""}>
            {p.kind === "baseline" ? p.label : p.kind === "now" ? "now" : `r${p.baseline_revision}`}
          </li>
        ))}
      </ol>
      <span className="small">
        <strong>{point.label}</strong> · {when(point.at)}
        {point.id !== null && " · read-only"}
      </span>
    </div>
  );
}
