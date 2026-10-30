import React from "react";
import { RequirementBadge } from "./Badge";

export interface RequirementCardProps {
  id: string; // e.g. "R12"
  title: string; // e.g. "Inactivity logout"
  version?: string; // e.g. "v1.4"
  body: string; // The requirement statement
  category?: string; // e.g. "Security requirements"
  section?: string; // e.g. "§3.2"
  owner?: string; // e.g. "Priya Shah"
  className?: string;
  accentColor?: "amber" | "blue" | "slate";
}

export function RequirementCard({
  id,
  title,
  version = "v1.4",
  body,
  category,
  section,
  owner,
  className = "",
  accentColor = "amber",
}: RequirementCardProps) {
  const borderAccents = {
    amber: "border-l-amber-500 bg-amber-50/20",
    blue: "border-l-blue-500 bg-blue-50/20",
    slate: "border-l-slate-400 bg-slate-50/40",
  };

  const footerParts = [category, section, owner ? `Owner: ${owner}` : null].filter(
    Boolean
  );

  return (
    <div
      className={`bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col justify-between ${className}`}
    >
      <div className="p-5">
        <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <RequirementBadge reqId={id} />
            <h3 className="font-semibold text-slate-900 text-sm">{title}</h3>
          </div>
          {version && (
            <span className="text-xs font-mono text-slate-400 font-medium">
              {version}
            </span>
          )}
        </div>

        <div
          className={`border-l-4 pl-3.5 py-1.5 rounded-r my-2 ${borderAccents[accentColor]}`}
        >
          <p className="text-sm font-semibold text-slate-900 leading-relaxed">
            {body}
          </p>
        </div>
      </div>

      {footerParts.length > 0 && (
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 text-xs text-slate-500 font-medium">
          {footerParts.join(" · ")}
        </div>
      )}
    </div>
  );
}
