import { Badge } from "../../components/Badge";

export interface ProtectedBadgeProps {
  reason?: string | null;
  /** Shorter wording for dense places (cards, table cells). */
  compact?: boolean;
}

/** The protected flag (Abhijeet — US-18, FR-21): a flag icon and a word, never colour alone, and
 *  screen readers hear that a compliance reviewer must decide. */
export function ProtectedBadge({ reason, compact = false }: ProtectedBadgeProps) {
  const title = reason ? `Protected: ${reason}` : "Protected: changes need a compliance reviewer";
  return (
    <Badge tone="neutral" icon="⚑" title={title}>
      Protected
      {!compact && <span className="sr-only"> — a compliance reviewer must approve changes</span>}
    </Badge>
  );
}
