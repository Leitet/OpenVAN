# OpenVan Design System (in-repo)

The OpenVan design tokens, wired into the simulator. Two layers:

- **Product / OS** — `--ov-app-*` (`tokens/product.css`): the dark "tech OS" the
  simulator uses. This is what product UI should consume.
- **Brand / Persona** — `--ov-*` (`tokens/colors.css`): warm per-persona palettes
  (`[data-theme="aurora|forge|nomad|pulse|ranger|scout"]`) for marketing / the
  persona trading cards. In this app the persona cards are images
  (`public/personalities/*.jpg`), so these tokens are here for future brand UI.

## How it's wired

- `main.tsx` imports `design-system/styles.css` **before** `index.css`.
- `index.css`'s `:root` aliases the app's short vars onto the DS tokens
  (`--bg: var(--ov-app-bg)`, …), so every existing `var(--bg)` keeps working and
  the palette now lives in one place. New product surfaces should use the
  `--ov-app-*` tokens (and `--ov-space-*`, `--ov-radius-*`, `--ov-text-*`) directly.

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
