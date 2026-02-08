from __future__ import annotations

import secrets
import time

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CROCKFORD32_SET = set(_CROCKFORD32)


def ulid_new(*, now_ms: int | None = None) -> str:
    """
    Generate a ULID (26-char Crockford Base32, uppercase).

    Layout:
    - 48 bits timestamp (ms)
    - 80 bits randomness
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    now_ms &= (1 << 48) - 1
    rand = int.from_bytes(secrets.token_bytes(10), "big", signed=False)
    value = (now_ms << 80) | rand

    out = []
    for _ in range(26):
        out.append(_CROCKFORD32[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def ulid_is_valid(s: str) -> bool:
    s = (s or "").strip()
    if len(s) != 26:
        return False
    if s.upper() != s:
        return False
    return all(ch in _CROCKFORD32_SET for ch in s)


def ulid_is_placeholder(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return True
    if "MINT_WITH_SCC_OID_GENERATOR" in s:
        return True
    if s.startswith("<") and s.endswith(">"):
        return True
    return False

