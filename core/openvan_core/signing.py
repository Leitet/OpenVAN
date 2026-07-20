"""Driver signing — Ed25519 over a canonical package digest, pure stdlib.

The trust chain for the driver ecosystem: the OpenVan store (or any publisher)
signs a driver package; Core verifies before loading and shows the provenance.
Users may still run unsigned drivers (their van, their call) — but a package whose
**signature no longer matches its contents is refused outright**: "signed then
tampered" is the one state that must never run.

Why hand-written Ed25519? Core stays dependency-light on the edge (the same rule
as the stdlib Modbus/MQTT clients). Verification operates on *public* data with a
*public* key — no secrets, no timing-sensitive material on the van. The
implementation follows RFC 8032 directly and is pinned by the RFC's own test
vectors in ``tests/test_signing.py``. (Signing happens on a publisher's machine
via the CLI; swap in a hardware key or `cryptography` there later if desired.)

CLI (console script ``openvan-driver``):

    openvan-driver keygen  <name>            # -> <name>.key (secret) + <name>.pub
    openvan-driver sign    <driver-dir> --key <name>.key
    openvan-driver verify  <driver-dir>

Digest: sha256 over every file in the package (sorted relative paths, path and
content both bound), excluding the ``SIGNATURE`` file itself and caches — so any
change to the manifest or any code changes the digest.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SIGNATURE_FILE = "SIGNATURE"
_EXCLUDE_DIRS = {"__pycache__", ".git"}

# --- Ed25519 (RFC 8032) -------------------------------------------------------

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


# Base point B
_By = 4 * _inv(5) % _P


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * pow(2, (_P - 1) // 4, _P) % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_Bx = _recover_x(_By, 0)
_B = (_Bx, _By, 1, _Bx * _By % _P)  # extended homogeneous coordinates
_IDENT = (0, 1, 1, 0)


def _point_add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _point_mul(s: int, p):
    q = _IDENT
    while s > 0:
        if s & 1:
            q = _point_add(q, p)
        p = _point_add(p, p)
        s >>= 1
    return q


def _point_equal(p, q) -> bool:
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _point_compress(p) -> bytes:
    x, y, z, _ = p
    zinv = _inv(z)
    x, y = x * zinv % _P, y * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _point_decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _secret_expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError("secret key must be 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public_key(secret: bytes) -> bytes:
    a, _ = _secret_expand(secret)
    return _point_compress(_point_mul(a, _B))


def ed25519_sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _secret_expand(secret)
    A = _point_compress(_point_mul(a, _B))
    r = int.from_bytes(_sha512(prefix + msg), "little") % _L
    Rs = _point_compress(_point_mul(r, _B))
    h = int.from_bytes(_sha512(Rs + A + msg), "little") % _L
    s = (r + h * a) % _L
    return Rs + int.to_bytes(s, 32, "little")


def ed25519_verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _point_decompress(public)
    if A is None:
        return False
    Rs = signature[:32]
    R = _point_decompress(Rs)
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(_sha512(Rs + public + msg), "little") % _L
    return _point_equal(_point_mul(s, _B), _point_add(R, _point_mul(h, A)))


# --- canonical driver digest --------------------------------------------------

def driver_digest(driver_dir: Path | str) -> bytes:
    """sha256 binding every file's path AND content (SIGNATURE + caches excluded)."""
    driver_dir = Path(driver_dir)
    entries: list[tuple[str, Path]] = []
    for root, dirs, files in os.walk(driver_dir):
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDE_DIRS)
        for name in sorted(files):
            if name == SIGNATURE_FILE or name.endswith(".pyc"):
                continue
            path = Path(root) / name
            entries.append((path.relative_to(driver_dir).as_posix(), path))
    outer = hashlib.sha256()
    for rel, path in sorted(entries):
        inner = hashlib.sha256(rel.encode() + b"\0" + path.read_bytes()).digest()
        outer.update(inner)
    return outer.digest()


# --- signature file ------------------------------------------------------------

def sign_driver(driver_dir: Path | str, secret: bytes) -> dict:
    """Write ``SIGNATURE`` next to the manifest; returns its payload."""
    driver_dir = Path(driver_dir)
    digest = driver_digest(driver_dir)
    payload = {
        "algo": "ed25519",
        "public_key": ed25519_public_key(secret).hex(),
        "signature": ed25519_sign(secret, digest).hex(),
    }
    (driver_dir / SIGNATURE_FILE).write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def read_signature(driver_dir: Path | str) -> dict | None:
    path = Path(driver_dir) / SIGNATURE_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        if data.get("algo") != "ed25519":
            return None
        bytes.fromhex(data["public_key"])
        bytes.fromhex(data["signature"])
        return data
    except (ValueError, KeyError, TypeError):
        return None


def verify_driver(driver_dir: Path | str) -> tuple[bool, bytes | None]:
    """(signature valid for its embedded key, that public key).

    ``(False, key)`` with a key present means: **signed but tampered** — the
    contents no longer match what the signer signed.
    """
    sig = read_signature(driver_dir)
    if sig is None:
        return False, None
    public = bytes.fromhex(sig["public_key"])
    ok = ed25519_verify(public, driver_digest(driver_dir), bytes.fromhex(sig["signature"]))
    return ok, public


# --- CLI -----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="openvan-driver", description="Sign and verify OpenVan drivers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("keygen", help="generate a signing key pair")
    g.add_argument("name")
    s = sub.add_parser("sign", help="sign a driver directory")
    s.add_argument("driver_dir")
    s.add_argument("--key", required=True, help="path to the .key secret file")
    v = sub.add_parser("verify", help="verify a driver directory's signature")
    v.add_argument("driver_dir")
    args = parser.parse_args(argv)

    if args.cmd == "keygen":
        secret = os.urandom(32)
        Path(f"{args.name}.key").write_bytes(secret)
        os.chmod(f"{args.name}.key", 0o600)
        Path(f"{args.name}.pub").write_text(ed25519_public_key(secret).hex() + "\n")
        print(f"wrote {args.name}.key (keep secret) and {args.name}.pub (publish)")
        return 0
    if args.cmd == "sign":
        secret = Path(args.key).read_bytes()
        payload = sign_driver(args.driver_dir, secret)
        print(f"signed {args.driver_dir} with key {payload['public_key'][:16]}…")
        return 0
    # verify
    ok, public = verify_driver(args.driver_dir)
    if public is None:
        print("no signature")
        return 1
    print(("VALID" if ok else "TAMPERED") + f" (key {public.hex()[:16]}…)")
    return 0 if ok else 2


if __name__ == "__main__":  # pragma: no cover - `python -m openvan_core.signing`
    raise SystemExit(main())
