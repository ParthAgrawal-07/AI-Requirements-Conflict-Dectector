import React from "react";

export interface ConfidenceBadgeProps {
  confidence: number; // 0..1 or 0..100
  showBar?: boolean;
  showTextLabel?: boolean;
  variant?: "pill" | "bar" | "compact";
  className?: string;
}

export function ConfidenceBadge({
  confidence,
  showBar = false,
  showTextLabel = true,
  variant = "pill",
  className = "",
}: ConfidenceBadgeProps) {
  // Normalize if passed as 0..1 or 0..100
  const normalized = confidence > 1 ? confidence : confidence * 100;
  const percentage = Math.round(normalized);

  let colorClasses = "text-emerald-700 bg-emerald-50 border-emerald-200";
  let barColor = "bg-emerald-500";
  let label = "High";

  if (percentage < 70) {
    colorClasses = "text-slate-600 bg-slate-100 border-slate-200";
    barColor = "bg-slate-500";
    label = "Low";
  } else if (percentage < 85) {
    colorClasses = "text-amber-700 bg-amber-50 border-amber-200";
    barColor = "bg-amber-500";
    label = "Medium";
  }

  if (variant === "compact") {
    return (
      <span className={`text-sm font-semibold text-slate-900 ${className}`}>
        {percentage}%
      </span>
    );
  }

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md border text-xs font-medium ${colorClasses} ${className}`}
      title={`Confidence score: ${percentage}% (${label})`}
    >
      <span className="font-semibold">{percentage}%</span>
      {showTextLabel && <span>AI confidence</span>}
      {showBar && (
        <div className="w-10 h-1.5 bg-slate-200/80 rounded-full overflow-hidden ml-1">
          <div
            className={`h-full rounded-full transition-all duration-300 ${barColor}`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      )}
    </div>
  );
}
