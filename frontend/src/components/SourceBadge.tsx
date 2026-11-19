import { Badge } from "./Badge";

export type Source = "AI" | "Rule" | "Person";

const ICON: Record<Source, string> = { AI: "AI", Rule: "§", Person: "◉" };
const TITLE: Record<Source, string> = {
  AI: "Found by AI analysis — analysis can miss issues",
  Rule: "Found by a rule check",
  Person: "Raised by a person",
};

/** Who found it (US-56, ADR-25): AI, Rule or Person — an icon and the word, never colour alone. */
export function SourceBadge({ source }: { source: Source }) {
  return (
    <Badge tone={source === "AI" ? "ai" : source === "Person" ? "info" : "neutral"} icon={ICON[source]} title={TITLE[source]}>
      {source}
    </Badge>
  );
}
