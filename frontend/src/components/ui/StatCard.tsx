import React from "react";

export interface StatCardProps {
  value: number | string;
  label: string;
  description?: string;
  valueColor?: string;
  icon?: React.ReactNode;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  onClick?: () => void;
  isSelected?: boolean;
  className?: string;
}

export function StatCard({
  value,
  label,
  description,
  valueColor = "text-slate-900",
  icon,
  trend,
  onClick,
  isSelected = false,
  className = "",
}: StatCardProps) {
  const isClickable = Boolean(onClick);

  return (
    <div
      onClick={onClick}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={`
        bg-white rounded-xl border p-5 shadow-sm transition-all duration-150
        flex items-start gap-4
        ${
          isSelected
            ? "border-blue-500 ring-2 ring-blue-100 shadow-md"
            : "border-slate-200"
        }
        ${
          isClickable
            ? "cursor-pointer hover:border-slate-300 hover:shadow"
            : ""
        }
        ${className}
      `}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-3">
          <span className={`text-3xl font-bold tracking-tight ${valueColor}`}>
            {value}
          </span>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold text-slate-900 truncate">
              {label}
            </h4>
            {description && (
              <p className="text-xs text-slate-500 truncate mt-0.5">
                {description}
              </p>
            )}
          </div>
        </div>

        {trend && (
          <div className="mt-2 flex items-center text-xs">
            <span
              className={`font-medium ${
                trend.isPositive ? "text-emerald-600" : "text-rose-600"
              }`}
            >
              {trend.value}
            </span>
          </div>
        )}
      </div>

      {icon && (
        <div className="p-2 rounded-lg bg-slate-50 text-slate-500 shrink-0">
          {icon}
        </div>
      )}
    </div>
  );
}
