"""Envelope encryption for exchange API credentials.

Standard-library-only authenticated encryption (no ``cryptography``
dependency): HMAC-SHA256 used as a PRF in CTR mode for confidentiality,
plus encrypt-then-MAC for integrity. Nonce is random per seal.

Construction:
    enc_key  = HKDF-like derivation: HMAC(master, b"enc"  || nonce)
    mac_key  = HKDF-like derivation: HMAC(master, b"mac"  || nonce)
    stream   = HMAC(enc_key, counter_bytes) blocks, XOR'd with plaintext
    tag      = HMAC(mac_key, nonce || ciphertext)

Security notes:
    - HMAC is a secure PRF, so CTR mode under it is IND-CPA.
    - Encrypt-then-MAC with a separate key prevents padding/CCA issues.
    - The per-seal random nonce (12 bytes) makes keystreams unique.
    - ``open()`` verifies the tag with ``hmac.compare_digest`` before
      releasing any plaintext.
"""

import base64
import hashlib
import hmac
import os

_NONCE_LEN = 12
_BLOCK_LEN = 32  # SHA-256 output size


class CredentialCryptoError(Exception):
    """Raised on tampering, wrong master key, or malformed ciphertext."""


def _derive(master_key: bytes, label: bytes, nonce: bytes) -> bytes:
    return hmac.new(master_key, label + nonce, hashlib.sha256).digest()


def _keystream(enc_key: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    while len(b"".join(blocks)) < length:
        blocks.append(hmac.new(enc_key, counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def seal_dict(master_key: bytes | str, payload: dict[str, str]) -> str:
    """Encrypt a credentials dict (api_key/secret/passphrase) → base64 token."""
    key = _normalize_key(master_key)
    nonce = os.urandom(_NONCE_LEN)
    plaintext = "\n".join(f"{k}={v}" for k, v in sorted(payload.items())).encode("utf-8")
    enc_key = _derive(key, b"enc", nonce)
    mac_key = _derive(key, b"mac", nonce)
    ciphertext = _xor(plaintext, _keystream(enc_key, len(plaintext)))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")


def open_dict(master_key: bytes | str, token: str) -> dict[str, str]:
    """Decrypt a seal_dict token back into a credentials dict.

    Raises CredentialCryptoError on tampering or wrong master key.
    """
    key = _normalize_key(master_key)
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError("malformed credential token (bad base64)") from exc
    if len(raw) < _NONCE_LEN + 32 + 1:
        raise CredentialCryptoError("malformed credential token (too short)")
    nonce = raw[:_NONCE_LEN]
    tag = raw[_NONCE_LEN:_NONCE_LEN + 32]
    ciphertext = raw[_NONCE_LEN + 32:]
    enc_key = _derive(key, b"enc", nonce)
    mac_key = _derive(key, b"mac", nonce)
    expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise CredentialCryptoError("credential token authentication failed (wrong master key or tampered)")
    plaintext = _xor(ciphertext, _keystream(enc_key, len(ciphertext)))
    try:
        text = plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialCryptoError("credential token decrypted to invalid utf-8") from exc
    out: dict[str, str] = {}
    for line in text.split("\n"):
        if not line:
            continue
        name, sep, value = line.partition("=")
        if not sep or not name:
            raise CredentialCryptoError("credential token payload malformed")
        out[name] = value
    return out


def _normalize_key(master_key: bytes | str) -> bytes:
    if isinstance(master_key, str):
        master_key = master_key.encode("utf-8")
    if len(master_key) < 16:
        raise CredentialCryptoError("master key must be at least 16 bytes")
    # Hash to a fixed 32-byte key regardless of input length.
    return hashlib.sha256(b"quant-cred-master:" + master_key).digest()
