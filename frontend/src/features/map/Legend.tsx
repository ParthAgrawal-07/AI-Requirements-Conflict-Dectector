/** What the map's shapes, borders and lines mean, in words (US-14, NFR-29: never colour alone). */
export function Legend() {
  return (
    <details className="map-legend">
      <summary>Legend</summary>
      <dl>
        <dt>Shape</dt>
        <dd>Rounded box: functional · oval: non-functional · diamond: constraint</dd>
        <dt>Border</dt>
        <dd>Solid: approved or implemented (the baseline) · dashed: proposed or under review · dotted and faded: rejected or deprecated · thick: protected</dd>
        <dt>Lines</dt>
        <dd>
          <span className="legend-line legend-conflict" aria-hidden="true" /> Solid red: conflict ·{" "}
          <span className="legend-line legend-duplicate" aria-hidden="true" /> dashed purple: possible duplicate ·{" "}
          <span className="legend-line legend-depends" aria-hidden="true" /> arrow: depends on · dotted grey: human
          link · thicker: High severity
        </dd>
        <dt>Badges</dt>
        <dd>“?” after the ID: ambiguous wording · “…”: missing information</dd>
      </dl>
    </details>
  );
}
