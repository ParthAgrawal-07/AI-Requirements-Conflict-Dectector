import type { ReactNode } from "react";

// Every badge carries an icon AND a word, so state never depends on colour alone (design rule).
export type BadgeTone = "approved" | "proposed" | "conflict" | "neutral" | "ai" | "info";

const ICONS: Record<BadgeTone, string> = {
  approved: "■",
  proposed: "▢",
  conflict: "✕",
  neutral: "—",
  ai: "AI",
  info: "i",
};

export interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  /** Override the default icon of the tone (e.g. "⚑" for protected). */
  icon?: string;
  title?: string;
}

export function Badge({ tone = "neutral", children, icon, title }: BadgeProps) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      <span className="badge-icon" aria-hidden="true">
        {icon ?? ICONS[tone]}
      </span>
      {children}
    </span>
  );
}
