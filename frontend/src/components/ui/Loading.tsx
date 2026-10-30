import React from "react";

export interface SpinnerProps {
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
  color?: string;
}

export function Spinner({
  size = "md",
  className = "",
  color = "text-blue-600",
}: SpinnerProps) {
  const sizeMap = {
    sm: "w-4 h-4",
    md: "w-6 h-6",
    lg: "w-8 h-8",
    xl: "w-12 h-12",
  };

  return (
    <svg
      className={`animate-spin ${sizeMap[size]} ${color} ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-label="Loading"
      role="status"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

export function Skeleton({
  className = "",
  variant = "rectangular",
  width,
  height,
}: {
  className?: string;
  variant?: "rectangular" | "circular" | "text";
  width?: string | number;
  height?: string | number;
}) {
  const roundedClass =
    variant === "circular"
      ? "rounded-full"
      : variant === "text"
      ? "rounded"
      : "rounded-lg";

  return (
    <div
      style={{ width, height }}
      className={`animate-pulse bg-slate-200/80 ${roundedClass} ${className}`}
      aria-hidden="true"
    />
  );
}

export interface ProgressBarProps {
  value: number; // 0..100
  label?: string;
  showValue?: boolean;
  color?: "blue" | "emerald" | "amber" | "indigo";
  className?: string;
}

export function ProgressBar({
  value,
  label,
  showValue = false,
  color = "blue",
  className = "",
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  const colors = {
    blue: "bg-blue-600",
    emerald: "bg-emerald-600",
    amber: "bg-amber-500",
    indigo: "bg-indigo-600",
  };

  return (
    <div className={`w-full space-y-1.5 ${className}`}>
      {(label || showValue) && (
        <div className="flex justify-between items-center text-xs text-slate-600">
          {label && <span className="font-medium">{label}</span>}
          {showValue && <span className="font-mono">{Math.round(clamped)}%</span>}
        </div>
      )}
      <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden border border-slate-200/50">
        <div
          className={`h-full transition-all duration-300 rounded-full ${colors[color]}`}
          style={{ width: `${clamped}%` }}
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}
