# Official store keys

Ed25519 public keys (hex, one per `.pub` file) whose signatures mark a driver as
**official** — signed by the OpenVan store. The matching private keys are held by
the OpenVan organisation (backed up in Bitwarden per the engineering standards)
and are never committed.

Users trust additional publisher keys by dropping `.pub` files into
`data/trust/` — drivers signed by those verify as **community**.

Generate a pair with: `openvan-driver keygen <name>` (commit/publish only the
`.pub`; guard the `.key`).
