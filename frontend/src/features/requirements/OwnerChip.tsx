export interface OwnerChipProps {
  ownerName: string | null;
  group: string | null;
}

/** Who owns a requirement and for which stakeholder group (US-36, interface design §6). */
export function OwnerChip({ ownerName, group }: OwnerChipProps) {
  return (
    <span className="owner-chip" title="Owner · stakeholder group">
      <span aria-hidden="true">👤</span> {ownerName ?? "Unassigned"}
      {group && <span className="muted"> · {group}</span>}
    </span>
  );
}
