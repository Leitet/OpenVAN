"""Driver signing: the Ed25519 implementation pinned against RFC 8032's official
test vectors, plus the canonical package digest and sign/verify/tamper flow."""

from __future__ import annotations

import pytest

from openvan_core.signing import (
    driver_digest,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
    read_signature,
    sign_driver,
    verify_driver,
)

# RFC 8032 §7.1 — TEST 1, TEST 2, TEST 3.
_VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize("secret,public,msg,sig", _VECTORS)
def test_rfc8032_vectors(secret, public, msg, sig):
    secret_b, public_b = bytes.fromhex(secret), bytes.fromhex(public)
    msg_b, sig_b = bytes.fromhex(msg), bytes.fromhex(sig)
    assert ed25519_public_key(secret_b) == public_b
    assert ed25519_sign(secret_b, msg_b) == sig_b
    assert ed25519_verify(public_b, msg_b, sig_b)
    # A flipped bit anywhere must fail.
    assert not ed25519_verify(public_b, msg_b + b"x", sig_b)
    assert not ed25519_verify(public_b, msg_b, sig_b[:-1] + bytes([sig_b[-1] ^ 1]))


def test_verify_rejects_malformed_inputs():
    assert not ed25519_verify(b"short", b"m", b"s" * 64)
    assert not ed25519_verify(b"\x00" * 32, b"m", b"s" * 63)


# --- package digest + sign/verify --------------------------------------------

def _make_driver(tmp_path):
    d = tmp_path / "acme_widget"
    (d / "acme_widget").mkdir(parents=True)
    (d / "driver.toml").write_text('[driver]\nid = "acme_widget"\n')
    (d / "acme_widget" / "__init__.py").write_text("VALUE = 1\n")
    return d


def test_digest_binds_paths_and_content(tmp_path):
    d = _make_driver(tmp_path)
    base = driver_digest(d)
    assert driver_digest(d) == base  # stable
    (d / "acme_widget" / "__init__.py").write_text("VALUE = 2\n")
    assert driver_digest(d) != base  # content changes it
    (d / "acme_widget" / "__init__.py").write_text("VALUE = 1\n")
    (d / "acme_widget" / "extra.py").write_text("")
    assert driver_digest(d) != base  # a new file changes it


def test_sign_verify_and_tamper(tmp_path):
    d = _make_driver(tmp_path)
    secret = bytes(range(32))
    sign_driver(d, secret)
    assert read_signature(d) is not None

    ok, public = verify_driver(d)
    assert ok and public == ed25519_public_key(secret)

    # Tamper with the code after signing → signature present but INVALID.
    (d / "acme_widget" / "__init__.py").write_text("import os  # evil\n")
    ok, public = verify_driver(d)
    assert not ok and public == ed25519_public_key(secret)


def test_unsigned_driver_reports_no_signature(tmp_path):
    d = _make_driver(tmp_path)
    ok, public = verify_driver(d)
    assert not ok and public is None
