import React, { useState } from "react";
import { TopNav } from "./TopNav";
import { Sidebar } from "./Sidebar";

export interface PageLayoutProps {
  currentPath: string;
  onNavigate: (href: string) => void;
  children: React.ReactNode;
  footerLeft?: React.ReactNode;
  footerRight?: React.ReactNode;
  className?: string;
}

export function PageLayout({
  currentPath,
  onNavigate,
  children,
  footerLeft = "Latest analysis: 12 Oct 2026, 09:20 · All findings require human review",
  footerRight = "Requirements baseline v1.4",
  className = "",
}: PageLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900">
      <TopNav onMenuToggle={() => setSidebarOpen(!sidebarOpen)} />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          currentPath={currentPath}
          onNavigate={onNavigate}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
          <div className={`flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 ${className}`}>
            {children}
          </div>

          <footer className="border-t border-slate-200/80 bg-white/60 px-4 sm:px-6 lg:px-8 py-3 text-xs text-slate-400 flex flex-col sm:flex-row items-center justify-between gap-2 mt-auto">
            <div>{footerLeft}</div>
            <div>{footerRight}</div>
          </footer>
        </main>
      </div>
    </div>
  );
}
