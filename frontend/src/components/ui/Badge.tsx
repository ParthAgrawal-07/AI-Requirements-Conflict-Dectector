import React from "react";
import { FindingCategory, FindingStatus, Severity } from "../../types";

export type TrustSource = "AI" | "Rule" | "Person";

export type DisplayStatus =
  | FindingStatus
  | "Pending Review"
  | "Awaiting Clarification"
  | "Resolved"
  | "Accepted"
  | "Dismissed"
  | "pending"
  | "awaiting_clarification"
  | "resolved"
  | "accepted";

export type DisplaySeverity = Severity | "High" | "Medium" | "Low" | "Critical";

interface BaseBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children?: React.ReactNode;
}

export function CategoryBadge({
  category,
  className = "",
}: {
  category: FindingCategory;
  className?: string;
}) {
  const styles: Record<FindingCategory, string> = {
    Conflicting: "bg-red-50 text-red-700 border-red-200",
    Duplicate: "bg-amber-50 text-amber-700 border-amber-200",
    Ambiguous: "bg-purple-50 text-purple-700 border-purple-200",
    Incomplete: "bg-orange-50 text-orange-700 border-orange-200",
    Dependent: "bg-sky-50 text-sky-700 border-sky-200",
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${
        styles[category] ?? "bg-slate-50 text-slate-700 border-slate-200"
      } ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full mr-1.5 bg-current" />
      {category}
    </span>
  );
}

export function SeverityBadge({
  severity,
  className = "",
}: {
  severity: DisplaySeverity | string | null | undefined;
  className?: string;
}) {
  if (!severity) return null;

  const normalized = severity.toLowerCase() as Severity;

  const styles: Record<Severity, string> = {
    critical: "bg-rose-100 text-rose-800 border-rose-300 font-bold",
    high: "bg-red-50 text-red-700 border-red-200 font-semibold",
    medium: "bg-amber-50 text-amber-700 border-amber-200 font-semibold",
    low: "bg-blue-50 text-blue-700 border-blue-200 font-medium",
  };

  const labels: Record<Severity, string> = {
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low",
  };

  const badgeStyle = styles[normalized] || "bg-slate-100 text-slate-700 border-slate-200";
  const badgeLabel = labels[normalized] || severity;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs border ${badgeStyle} ${className}`}
    >
      {badgeLabel}
    </span>
  );
}

export function StatusBadge({
  status,
  className = "",
}: {
  status: DisplayStatus | string;
  className?: string;
}) {
  const normalized = status.toLowerCase().replace(/\s+/g, "_");

  let badgeStyle = "bg-slate-100 text-slate-700 border-slate-200";
  let label = status;

  if (normalized === "pending_review" || normalized === "flagged" || normalized === "pending") {
    badgeStyle = "bg-blue-50 text-blue-700 border-blue-200";
    label = "Pending Review";
  } else if (normalized === "awaiting_clarification") {
    badgeStyle = "bg-amber-50 text-amber-700 border-amber-200";
    label = "Awaiting Clarification";
  } else if (normalized === "resolved") {
    badgeStyle = "bg-emerald-50 text-emerald-700 border-emerald-200";
    label = "Resolved";
  } else if (normalized === "dismissed") {
    badgeStyle = "bg-slate-100 text-slate-500 border-slate-200";
    label = "Dismissed";
  } else if (normalized === "accepted" || normalized === "confirmed") {
    badgeStyle = "bg-teal-50 text-teal-700 border-teal-200";
    label = "Accepted";
  } else if (normalized === "merged") {
    badgeStyle = "bg-emerald-100 text-emerald-800 border-emerald-200";
    label = "Merged";
  } else if (normalized === "reclassified") {
    badgeStyle = "bg-indigo-100 text-indigo-800 border-indigo-200";
    label = "Reclassified";
  }

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium border ${badgeStyle} ${className}`}
    >
      {label}
    </span>
  );
}

export function RequirementBadge({
  reqId,
  className = "",
}: {
  reqId: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium bg-blue-50 text-blue-700 border border-blue-200 ${className}`}
    >
      {reqId}
    </span>
  );
}

export function SourceBadge({
  source,
  className = "",
}: {
  source: TrustSource;
  className?: string;
}) {
  const icons: Record<TrustSource, string> = {
    AI: "🤖",
    Rule: "📐",
    Person: "👤",
  };

  const styles: Record<TrustSource, string> = {
    AI: "bg-indigo-50 text-indigo-700 border-indigo-200",
    Rule: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Person: "bg-slate-100 text-slate-700 border-slate-300",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${styles[source]} ${className}`}
      title={`Raised by ${source}`}
    >
      <span role="img" aria-label={source}>
        {icons[source]}
      </span>
      <span>{source}</span>
    </span>
  );
}

export function Badge({
  children,
  className = "",
  variant = "default",
}: BaseBadgeProps & { variant?: "default" | "outline" | "subtle" }) {
  const variantStyles = {
    default: "bg-slate-100 text-slate-700 border-slate-200",
    outline: "border border-slate-300 text-slate-600 bg-transparent",
    subtle: "bg-slate-50 text-slate-600 border-transparent",
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
