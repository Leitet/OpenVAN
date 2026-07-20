// Cross-tab navigation without prop drilling. App listens for the event and
// switches tab; a target sub-view that mounts *because of* the event would miss
// it, so the pending value is stashed for the mounting component to consume.

let pendingSettings: string | null = null;

export function navigateTo(tab: string, settings?: string) {
  if (settings) pendingSettings = settings;
  window.dispatchEvent(
    new CustomEvent("openvan:navigate", { detail: { tab, settings } }),
  );
}

// Peek + clear are separate so a React StrictMode double-invoked initializer
// (which would consume the value on the throwaway render) can't lose it: read
// in the useState initializer, clear in a mount effect.
export function peekPendingSettings(): string | null {
  return pendingSettings;
}

export function clearPendingSettings(): void {
  pendingSettings = null;
}
