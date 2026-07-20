"""AES-128 pinned by the FIPS-197 appendix C.1 vector, plus CTR properties."""

from __future__ import annotations

from openvan_core.aesctr import aes128_ctr, aes128_encrypt_block


def test_fips197_vector():
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")
    expected = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    assert aes128_encrypt_block(key, plaintext) == expected


def test_ctr_roundtrip_and_iv_sensitivity():
    key = bytes(range(16))
    data = b"victron instant readout payload!!"  # >1 block → counter increments
    ct = aes128_ctr(key, 0x1234, data)
    assert ct != data
    assert aes128_ctr(key, 0x1234, ct) == data  # CTR is symmetric
    assert aes128_ctr(key, 0x1235, ct) != data  # wrong iv → garbage


def test_ctr_partial_block():
    key = bytes(16)
    assert len(aes128_ctr(key, 1, b"abc")) == 3
