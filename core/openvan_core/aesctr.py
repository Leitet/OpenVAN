"""AES-128-CTR, pure stdlib — for decrypting Victron BLE Instant Readout.

Same rationale as the Ed25519 in ``signing.py``: the edge runtime stays
dependency-light, and this decrypts *broadcast* data with a key the user supplies
— no secret generation, no TLS, no timing-sensitive server surface. The S-box is
**generated** (GF(2^8) inverse + affine transform), not typed in, and the whole
cipher is pinned by the FIPS-197 appendix vector in ``tests/test_aesctr.py`` —
if any table or round is wrong, the vector fails.

CTR layout matches pycryptodome's ``Counter.new(128, initial_value=iv,
little_endian=True)`` as used by the Victron ecosystem: counter block *i* is the
128-bit little-endian encoding of ``iv + i``.
"""

from __future__ import annotations


def _make_sbox() -> list[int]:
    def _rotl8(x: int, n: int) -> int:
        return ((x << n) | (x >> (8 - n))) & 0xFF

    sbox = [0] * 256
    p = q = 1
    sbox[0] = 0x63
    while True:
        # p *= 3 in GF(2^8)
        p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        # q /= 3 (multiply by the inverse of 3)
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        sbox[p] = (q ^ _rotl8(q, 1) ^ _rotl8(q, 2) ^ _rotl8(q, 3) ^ _rotl8(q, 4) ^ 0x63) & 0xFF
        if p == 1:
            break
    return sbox


_SBOX = _make_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _expand_key(key: bytes) -> list[list[int]]:
    if len(key) != 16:
        raise ValueError("AES-128 key must be 16 bytes")
    words = [list(key[i : i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        temp = list(words[i - 1])
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]  # RotWord
            temp = [_SBOX[b] for b in temp]  # SubWord
            temp[0] ^= _RCON[i // 4 - 1]
        words.append([a ^ b for a, b in zip(words[i - 4], temp)])
    # Round key r as a flat 16-byte list, column-major like the state.
    return [[words[4 * r + c][row] for c in range(4) for row in range(4)] for r in range(11)]
    # note: index below uses state[row + 4*col]; round key laid out to match


def _encrypt_block(state_in: bytes, round_keys: list[list[int]]) -> bytes:
    # State: s[row + 4*col] = input[row + 4*col] (FIPS column-major fill).
    s = list(state_in)

    def add_round_key(r: int) -> None:
        rk = round_keys[r]
        for col in range(4):
            for row in range(4):
                s[row + 4 * col] ^= rk[4 * col + row]

    def sub_bytes() -> None:
        for i in range(16):
            s[i] = _SBOX[s[i]]

    def shift_rows() -> None:
        for row in range(1, 4):
            vals = [s[row + 4 * col] for col in range(4)]
            vals = vals[row:] + vals[:row]
            for col in range(4):
                s[row + 4 * col] = vals[col]

    def mix_columns() -> None:
        for col in range(4):
            a = [s[row + 4 * col] for row in range(4)]
            t = a[0] ^ a[1] ^ a[2] ^ a[3]
            u = a[0]
            s[0 + 4 * col] ^= t ^ _xtime(a[0] ^ a[1])
            s[1 + 4 * col] ^= t ^ _xtime(a[1] ^ a[2])
            s[2 + 4 * col] ^= t ^ _xtime(a[2] ^ a[3])
            s[3 + 4 * col] ^= t ^ _xtime(a[3] ^ u)

    add_round_key(0)
    for r in range(1, 10):
        sub_bytes()
        shift_rows()
        mix_columns()
        add_round_key(r)
    sub_bytes()
    shift_rows()
    add_round_key(10)
    return bytes(s)


def aes128_encrypt_block(key: bytes, block: bytes) -> bytes:
    if len(block) != 16:
        raise ValueError("block must be 16 bytes")
    return _encrypt_block(block, _expand_key(key))


def aes128_ctr(key: bytes, iv: int, data: bytes) -> bytes:
    """Encrypt/decrypt (symmetric) with a little-endian 128-bit counter starting
    at ``iv`` — the layout the Victron BLE ecosystem uses."""
    round_keys = _expand_key(key)
    out = bytearray()
    for i in range(0, len(data), 16):
        stream = _encrypt_block(((iv + i // 16) & ((1 << 128) - 1)).to_bytes(16, "little"), round_keys)
        chunk = data[i : i + 16]
        out += bytes(a ^ b for a, b in zip(chunk, stream))
    return bytes(out)
