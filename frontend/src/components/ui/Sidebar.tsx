import React from "react";
import {
  UploadCloudIcon,
  FileTextIcon,
  AlertTriangleIcon,
  BarChart2Icon,
  NetworkIcon,
  LayersIcon,
  SparklesIcon,
} from "./Icons";

export interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  href: string;
  badge?: string | number;
}

export interface SidebarProps {
  currentPath: string;
  onNavigate: (href: string) => void;
  isOpen?: boolean;
  onClose?: () => void;
  className?: string;
}

export function Sidebar({
  currentPath,
  onNavigate,
  isOpen = false,
  onClose,
  className = "",
}: SidebarProps) {
  const navItems: NavItem[] = [
    {
      id: "findings",
      label: "Findings",
      icon: <AlertTriangleIcon size={18} />,
      href: "/findings",
      badge: "6",
    },
    {
      id: "requirements",
      label: "Requirements",
      icon: <FileTextIcon size={18} />,
      href: "/requirements",
    },
    {
      id: "upload",
      label: "Upload SRS",
      icon: <UploadCloudIcon size={18} />,
      href: "/upload",
    },
    {
      id: "dashboard",
      label: "Dashboard",
      icon: <BarChart2Icon size={18} />,
      href: "/dashboard",
    },
    {
      id: "graph",
      label: "Graph View",
      icon: <NetworkIcon size={18} />,
      href: "/graph",
    },
    {
      id: "reports",
      label: "Reports",
      icon: <LayersIcon size={18} />,
      href: "/reports",
    },
    {
      id: "components",
      label: "UI Showcase",
      icon: <SparklesIcon size={18} />,
      href: "/components",
    },
  ];

  const handleItemClick = (href: string) => {
    onNavigate(href);
    if (onClose) onClose();
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/40 z-30 md:hidden backdrop-blur-xs"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`
          fixed md:static inset-y-0 left-0 z-40 w-60 bg-white border-r border-slate-200 flex flex-col justify-between shrink-0 transition-transform duration-200 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          ${className}
        `}
      >
        <div className="p-3 space-y-1 overflow-y-auto">
          <div className="px-3 py-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
            Workspace
          </div>
          {navItems.map((item) => {
            const isActive =
              currentPath === item.href ||
              (item.href === "/findings" && currentPath.startsWith("/findings"));

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleItemClick(item.href)}
                className={`
                  w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors text-left
                  ${
                    isActive
                      ? "bg-blue-50 text-blue-700 font-semibold"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100/70"
                  }
                `}
              >
                <div className="flex items-center gap-2.5">
                  <span
                    className={
                      isActive ? "text-blue-600" : "text-slate-400 group-hover:text-slate-600"
                    }
                  >
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span
                    className={`
                      px-1.5 py-0.5 rounded-full text-xs font-semibold
                      ${
                        isActive
                          ? "bg-blue-100 text-blue-700"
                          : "bg-slate-100 text-slate-600"
                      }
                    `}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="p-3 border-t border-slate-100 text-xs text-slate-400">
          <div className="px-3 py-1 font-mono text-[11px]">
            Sprint 1 · v0.1.0
          </div>
        </div>
      </aside>
    </>
  );
}
