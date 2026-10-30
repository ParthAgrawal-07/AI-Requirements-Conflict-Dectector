import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "muted" | "flat";
  isInteractive?: boolean;
}

export function Card({
  className = "",
  variant = "default",
  isInteractive = false,
  children,
  ...props
}: CardProps) {
  const variantStyles = {
    default: "bg-white border-slate-200 shadow-sm",
    muted: "bg-slate-50/70 border-slate-200/80 shadow-none",
    flat: "bg-white border-slate-200 shadow-none",
  };

  return (
    <div
      className={`
        rounded-xl border transition-all duration-150 overflow-hidden
        ${variantStyles[variant]}
        ${isInteractive ? "cursor-pointer hover:border-slate-300 hover:shadow" : ""}
        ${className}
      `}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={`text-base font-semibold leading-6 text-slate-900 ${className}`}
      {...props}
    >
      {children}
    </h3>
  );
}

export function CardDescription({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={`mt-0.5 text-xs text-slate-500 ${className}`} {...props}>
      {children}
    </p>
  );
}

export function CardContent({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`p-4 sm:p-5 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`p-4 sm:p-5 bg-slate-50/75 border-t border-slate-100 flex items-center justify-between gap-3 text-xs text-slate-500 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
