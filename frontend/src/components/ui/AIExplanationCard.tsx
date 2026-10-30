import React from "react";
import { SparklesIcon } from "./Icons";
import { SeverityBadge } from "./Badge";
import { ConfidenceBadge } from "./ConfidenceBadge";

export interface AIExplanationCardProps {
  title?: string;
  severity?: string;
  confidence: number;
  explanation: string;
  recommendation?: string;
  className?: string;
}

export function AIExplanationCard({
  title = "AI explanation",
  severity = "High",
  confidence = 0.92,
  explanation,
  recommendation,
  className = "",
}: AIExplanationCardProps) {
  return (
    <div
      className={`bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4 ${className}`}
    >
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-slate-900 font-semibold text-base">
          <SparklesIcon className="text-blue-600" size={18} />
          <span>{title}</span>
        </div>
        <div className="flex items-center gap-2">
          {severity && <SeverityBadge severity={severity} />}
          <ConfidenceBadge confidence={confidence} />
        </div>
      </div>

      <p className="text-sm text-slate-700 leading-relaxed">{explanation}</p>

      {recommendation && (
        <div className="bg-blue-50/70 border border-blue-100 rounded-lg p-3 text-xs text-blue-900 leading-relaxed font-medium">
          {recommendation}
        </div>
      )}
    </div>
  );
}
