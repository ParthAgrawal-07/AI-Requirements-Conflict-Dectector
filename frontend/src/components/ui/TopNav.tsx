import React from "react";
import { AppLogoIcon } from "./Icons";

export interface TopNavProps {
  appName?: string;
  projectName?: string;
  userName?: string;
  userRole?: string;
  userInitials?: string;
  onMenuToggle?: () => void;
  className?: string;
}

export function TopNav({
  appName = "Requirements Conflict Detector",
  projectName = "Atlas · Customer Portal",
  userName = "Abhijeet",
  userRole = "Reviewer",
  userInitials = "AB",
  onMenuToggle,
  className = "",
}: TopNavProps) {
  return (
    <header
      className={`h-14 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between z-20 shrink-0 ${className}`}
    >
      <div className="flex items-center gap-3">
        {onMenuToggle && (
          <button
            type="button"
            onClick={onMenuToggle}
            className="md:hidden p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 focus:outline-none"
            aria-label="Toggle navigation menu"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
        )}

        <div className="flex items-center gap-2.5">
          <AppLogoIcon size={26} />
          <div className="flex items-center gap-1.5 text-sm">
            <span className="font-semibold text-slate-900 tracking-tight">
              {appName}
            </span>
            <span className="text-slate-400 font-normal">/</span>
            <span className="text-slate-600 font-normal hidden sm:inline">
              {projectName}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 pl-3">
          <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-semibold text-xs border border-blue-200">
            {userInitials}
          </div>
          <div className="hidden sm:block text-left text-xs leading-tight">
            <div className="font-semibold text-slate-900">{userName}</div>
            <div className="text-slate-500">{userRole}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
