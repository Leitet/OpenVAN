import type { ReactNode } from "react";

// Minimal stroke icons (currentColor) so they inherit the active persona theme.
const PATHS: Record<string, ReactNode> = {
  home: (
    <>
      <path d="M3 11l9-7 9 7" />
      <path d="M5 10v9h14v-9" />
    </>
  ),
  power: <path d="M13 3L5 13h5l-1 8 8-11h-5z" />,
  comfort: (
    <>
      <path d="M10 13V6a2 2 0 114 0v7a4 4 0 11-4 0z" />
      <path d="M12 13v3" />
    </>
  ),
  journey: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5l-2 5-5 2 2-5z" />
    </>
  ),
  assistant: <path d="M20 12a8 8 0 01-11.6 7.1L4 20l1-4.3A8 8 0 1120 12z" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5l2.6-1.5M17.2 9l2.6-1.5" />
    </>
  ),
  bulb: (
    <>
      <path d="M9.5 18h5" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 00-4 10.5c.7.6 1 1.2 1 2h6c0-.8.3-1.4 1-2A6 6 0 0012 3z" />
    </>
  ),
  flame: <path d="M12 3s5 4 5 9a5 5 0 01-10 0c0-2 1-3 1-3s0 2 1.5 2S12 8 12 3z" />,
  drop: <path d="M12 3s6 6.5 6 11a6 6 0 01-12 0c0-4.5 6-11 6-11z" />,
};

export function NavIcon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" className="nav-ico" aria-hidden="true">
      {PATHS[name] ?? null}
    </svg>
  );
}
