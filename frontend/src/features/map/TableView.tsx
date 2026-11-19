import type { EdgeKind, GraphEdge, GraphNode } from "./api";

export interface TableViewProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  names: Map<string, string>;
  onSelect: (requirementId: string) => void;
}

export const KIND_WORDS: Record<EdgeKind, string> = {
  conflict: "conflicts with",
  duplicate: "may duplicate",
  depends_on: "depends on",
  ambiguous: "has ambiguous wording",
  incomplete: "is missing information",
  link: "is linked to",
};

/** The map as tables (US-14 AC: "a table view shows the same data"): what a screen reader, a
 *  keyboard or a 500-node graph on a small screen needs. */
export function TableView({ nodes, edges, names, onSelect }: TableViewProps) {
  const labels = new Map(nodes.map((node) => [node.id, node.label ?? "Unnumbered"]));
  const counts = new Map<string, number>();
  for (const edge of edges) {
    counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1);
    if (edge.target !== edge.source) counts.set(edge.target, (counts.get(edge.target) ?? 0) + 1);
  }
  return (
    <div className="map-tables">
      <table className="table">
        <caption>Requirements ({nodes.length})</caption>
        <thead>
          <tr>
            <th scope="col">ID</th>
            <th scope="col">State</th>
            <th scope="col">Type</th>
            <th scope="col">Group</th>
            <th scope="col">Owner</th>
            <th scope="col">Findings</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((node) => (
            <tr key={node.id}>
              <td>
                <button type="button" className="link-button mono" onClick={() => onSelect(node.id)}>
                  {labels.get(node.id)}
                </button>
                {node.is_protected && <span aria-label="Protected"> ⚑</span>}
              </td>
              <td>{node.state.replace("_", " ")}</td>
              <td>{node.req_type?.replace("_", "-") ?? "—"}</td>
              <td>{node.group ?? "—"}</td>
              <td>{node.owner_id ? (names.get(node.owner_id) ?? "A member") : "Unassigned"}</td>
              <td>{counts.get(node.id) ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="table">
        <caption>Relationships ({edges.length})</caption>
        <thead>
          <tr>
            <th scope="col">Relationship</th>
            <th scope="col">Review</th>
            <th scope="col">Severity</th>
            <th scope="col">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {edges.map((edge) => (
            <tr key={edge.id}>
              <td>
                {labels.get(edge.source) ?? "—"} {KIND_WORDS[edge.kind]}
                {edge.source !== edge.target && ` ${labels.get(edge.target) ?? "—"}`}
              </td>
              <td>{edge.status}</td>
              <td>{edge.severity ?? "—"}</td>
              <td>{edge.confidence !== null ? `${Math.round(edge.confidence * 100)}%` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
