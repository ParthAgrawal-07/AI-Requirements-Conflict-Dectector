import React from "react";

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface PageHeaderProps {
  breadcrumbs?: BreadcrumbItem[];
  title: string;
  description?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  breadcrumbs,
  title,
  description,
  badge,
  actions,
  className = "",
}: PageHeaderProps) {
  return (
    <div className={`space-y-1.5 pb-5 ${className}`}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="flex items-center space-x-1.5 text-xs font-semibold tracking-wider uppercase text-slate-400">
          {breadcrumbs.map((crumb, idx) => {
            const isLast = idx === breadcrumbs.length - 1;
            return (
              <React.Fragment key={crumb.label}>
                {idx > 0 && <span className="text-slate-300">/</span>}
                {crumb.onClick || crumb.href ? (
                  <button
                    type="button"
                    onClick={crumb.onClick}
                    className="hover:text-blue-600 transition-colors uppercase font-semibold"
                  >
                    {crumb.label}
                  </button>
                ) : (
                  <span className={isLast ? "text-slate-600" : ""}>
                    {crumb.label}
                  </span>
                )}
              </React.Fragment>
            );
          })}
        </nav>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-1">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {title}
          </h1>
          {badge && <div className="shrink-0">{badge}</div>}
        </div>

        {actions && (
          <div className="flex items-center gap-2.5 shrink-0">{actions}</div>
        )}
      </div>

      {description && (
        <p className="text-sm text-slate-500 max-w-3xl leading-relaxed">
          {description}
        </p>
      )}
    </div>
  );
}
