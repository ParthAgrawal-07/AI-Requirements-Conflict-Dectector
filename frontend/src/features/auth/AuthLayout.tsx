import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

/** The two-panel frame of the Sign in board: a static map on paper, the form on the right. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-layout">
      <aside className="auth-art grid-paper" aria-hidden="true">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="logo">RCD</span>
          <strong>Requirements Conflict Detector</strong>
        </div>
        <svg viewBox="0 0 460 300" width="100%" role="presentation">
          <g fontFamily="var(--font-mono)" fontSize="12">
            <line x1="90" y1="50" x2="230" y2="150" stroke="#1b1b1d" strokeWidth="1.5" />
            <line x1="90" y1="50" x2="100" y2="240" stroke="#1b1b1d" strokeWidth="1.5" />
            <line x1="230" y1="150" x2="100" y2="240" stroke="#9a948a" strokeWidth="1.5" />
            <line x1="230" y1="150" x2="380" y2="70" stroke="#c2410c" strokeWidth="2.5" />
            <line x1="230" y1="150" x2="370" y2="260" stroke="#1b1b1d" strokeDasharray="2 4" />
            <circle cx="305" cy="110" r="10" fill="#faf8f3" stroke="#c2410c" strokeWidth="2" />
            <text x="299" y="114" fill="#c2410c">✕</text>
            <text x="320" y="140" fill="#c2410c">conflict</text>
            <text x="270" y="220" fill="#4a4a4f">depends on</text>
            {[
              [40, 35, "REQ-002", false],
              [180, 136, "REQ-014", false],
              [330, 56, "REQ-031", true],
              [50, 226, "REQ-009", false],
              [320, 246, "REQ-040", true],
            ].map(([x, y, label, dashed]) => (
              <g key={String(label)}>
                <rect
                  x={Number(x)}
                  y={Number(y)}
                  width="100"
                  height="30"
                  rx="4"
                  fill="#faf8f3"
                  stroke={dashed ? "#c2410c" : "#1b1b1d"}
                  strokeDasharray={dashed ? "4 3" : undefined}
                />
                <text x={Number(x) + 18} y={Number(y) + 19} fill="#1b1b1d">
                  {String(label)}
                </text>
              </g>
            ))}
          </g>
        </svg>
        <p style={{ fontSize: 18, maxWidth: 360 }}>
          Every requirement your team writes, checked against everything you already agreed.
        </p>
      </aside>
      <main className="auth-panel">
        <div className="auth-form">{children}</div>
      </main>
    </div>
  );
}

/** "Sign in | Join with a code" switch shared by both screens (links, not ARIA tabs:
 *  each is its own page with its own URL). */
export function AuthSwitch() {
  return (
    <nav className="tab-list" aria-label="Account">
      <NavLink to="/login" className="tab" style={({ isActive }) => tabStyle(isActive)}>
        Sign in
      </NavLink>
      <NavLink to="/signup" className="tab" style={({ isActive }) => tabStyle(isActive)}>
        Join with a code
      </NavLink>
    </nav>
  );
}

function tabStyle(active: boolean) {
  return {
    flex: 1,
    textAlign: "center" as const,
    textDecoration: "none",
    color: active ? "var(--ink)" : "var(--ink-soft)",
    borderBottomColor: active ? "var(--ink)" : "transparent",
  };
}
