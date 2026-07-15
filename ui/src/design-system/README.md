# OpenVan Design System (in-repo)

The OpenVan design tokens, wired into the simulator. Two layers:

- **Product / OS** — `--ov-app-*` (`tokens/product.css`): the dark "tech OS" the
  simulator uses. This is what product UI should consume.
- **Brand / Persona** — `--ov-*` (`tokens/colors.css`): warm per-persona palettes
  (`[data-theme="aurora|forge|nomad|pulse|ranger|scout"]`) for marketing / the
  persona trading cards. In this app the persona cards are images
  (`public/personalities/*.jpg`), so these tokens are here for future brand UI.

## How it's wired — the UI themes to the active persona

- `main.tsx` imports `design-system/styles.css` **before** `index.css`.
- `index.css`'s `:root` aliases the app's short vars onto the **persona** tokens
  (`--bg: var(--ov-bg)`, `--accent: var(--ov-accent)`, …). Those change per
  `[data-theme]`, which `App.tsx` sets on `<html>` from the active personality
  (`assistant.personality_id`). So **choosing Aurora skins the whole app in
  Aurora, Pulse in Pulse**, etc. — light personas (Aurora/Nomad/Scout) and dark
  ones (Forge/Pulse/Ranger) both work; switching re-themes live (WebSocket).
- Only **status colours** (`--good/--warn/--bad`), the **font**, `--on-accent`,
  and **shape/elevation** (`--ov-radius-*`, `--ov-shadow-*`, `--ov-space-*`) stay
  theme-neutral (from `product.css` / `spacing.css`). The product layer's fixed
  dark surface/text/accent tokens (`--ov-app-bg/panel/text/accent`) are **no
  longer used as the app's base** — the app is persona-themed instead.
- New product surfaces should use the short vars (`var(--bg)`, `var(--accent)`,
  …) so they inherit the active persona automatically.

## Offline-first note

`tokens/fonts.css` intentionally does **not** load webfonts from a CDN — OpenVan
must work offline. The product UI uses the system font stack; the brand type
tokens fall back to `system-ui`. To use the display fonts for brand UI, self-host
them (preferred) or uncomment the import in `fonts.css` (adds a network dep).

## Files

- `styles.css` — entry point (`@import` manifest).
- `tokens/` — `product.css`, `colors.css`, `typography.css`, `spacing.css`, `fonts.css`.
- `components-reference.md` — the DS's React component catalog (brand + core),
  source + prop contracts. Reference only; not imported by the app.

Source: `~/Downloads/design_handoff_openvan_ds` (design handoff).
