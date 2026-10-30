import React from "react";

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  badge?: React.ReactNode;
  helperText?: string;
  error?: string;
  showCharCount?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      className = "",
      label,
      badge,
      helperText,
      error,
      showCharCount,
      maxLength,
      value,
      id,
      rows = 4,
      ...props
    },
    ref
  ) => {
    const generatedId = React.useId();
    const textareaId = id || generatedId;
    const hasError = Boolean(error);
    const charCount = typeof value === "string" ? value.length : 0;

    return (
      <div className="w-full space-y-1.5">
        {(label || badge) && (
          <div className="flex items-center justify-between">
            {label && (
              <label
                htmlFor={textareaId}
                className="block text-xs font-semibold text-slate-700 tracking-wide"
              >
                {label}
              </label>
            )}
            {badge && <div>{badge}</div>}
          </div>
        )}
        <div className="relative">
          <textarea
            id={textareaId}
            ref={ref}
            rows={rows}
            value={value}
            maxLength={maxLength}
            aria-invalid={hasError}
            aria-describedby={
              hasError
                ? `${textareaId}-error`
                : helperText
                ? `${textareaId}-helper`
                : undefined
            }
            className={`
              w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 transition-colors
              focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:bg-slate-50 disabled:text-slate-500 disabled:cursor-not-allowed
              ${
                hasError
                  ? "border-red-300 focus:border-red-500 focus:ring-red-200"
                  : "border-slate-300 focus:border-blue-500 focus:ring-blue-100"
              }
              ${className}
            `}
            {...props}
          />
        </div>
        <div className="flex items-center justify-between">
          <div>
            {hasError ? (
              <p id={`${textareaId}-error`} className="text-xs text-red-600 font-medium">
                {error}
              </p>
            ) : helperText ? (
              <p id={`${textareaId}-helper`} className="text-xs text-slate-500">
                {helperText}
              </p>
            ) : null}
          </div>
          {showCharCount && maxLength && (
            <p className="text-xs text-slate-400 font-mono">
              {charCount}/{maxLength}
            </p>
          )}
        </div>
      </div>
    );
  }
);

Textarea.displayName = "Textarea";
