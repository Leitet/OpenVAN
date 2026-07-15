import { createContext, useContext } from "react";
import type { useVanState } from "@shared/useVanState";

// The whole app shares ONE live connection to Core. App calls useVanState()
// once and provides it here; every tab reads via useVan() — no extra sockets.
export type VanState = ReturnType<typeof useVanState>;

const VanCtx = createContext<VanState | null>(null);
export const VanProvider = VanCtx.Provider;

export function useVan(): VanState {
  const v = useContext(VanCtx);
  if (!v) throw new Error("useVan must be used within <VanProvider>");
  return v;
}

export function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}
