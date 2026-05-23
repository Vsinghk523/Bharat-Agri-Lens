"""Field-level encryption for at-rest PII protection.

The codebase already loads ``cpa_fernet_key`` from settings (in
``app/config.py``) but until this module landed nothing actually used it.
This file is the canonical place that key gets read; everything else just
declares ``Column(EncryptedString(...))`` and gets transparent
encrypt-at-write / decrypt-at-read.

Encryption: Fernet (cryptography library) — AES-128-CBC + HMAC-SHA256
with a random IV per call. Same plaintext yields different ciphertexts,
which is fine for fields we don't need to search on (address, crops,
etc.) but means **don't** wrap fields you index or look up by exact
value. ``user_email`` and ``mobile_no`` stay plaintext because the OTP
flow looks them up directly during sign-in.

Migration story:
- Existing plaintext values (before this module landed) are read back
  as-is — ``_decrypt`` returns the raw string when Fernet can't parse it.
  This is a deliberate forgiving path so the v0 deployment doesn't break
  the day this lands.
- New writes always encrypt. Once everyone re-saves their profile during
  onboarding, the plaintext fallback becomes dead code.

Column-width sizing:
- A Fernet token is base64-encoded and ~78 chars longer than the
  plaintext (versioning, timestamp, IV, HMAC). For a 200-char address
  the encrypted form is ~390 chars. ``EncryptedString(plaintext_len)``
  picks an underlying VARCHAR width that comfortably fits both
  ciphertext and any future plaintext fallback. The migration that
  introduces this type widens existing columns to match.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    """Process-wide Fernet instance.

    ``cpa_fernet_key`` MUST be a 32-byte url-safe base64-encoded value
    (generate with ``Fernet.generate_key().decode()``). Loaded once per
    process; the lru_cache also means a key rotation requires a process
    restart — intentional, since changing the key without re-encrypting
    existing rows would silently corrupt them.
    """
    s = get_settings()
    return Fernet(s.cpa_fernet_key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string. Returns a Fernet token (str)."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token. Returns the plaintext string.

    On invalid / unparseable input (e.g. legacy plaintext rows that
    pre-date this encryption pass) returns the input unchanged so the
    UI doesn't break. Caller can tell whether the value was encrypted
    by checking ``looks_encrypted()`` if needed.
    """
    if not token:
        return token
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        # Treat as plaintext legacy value.
        return token


def looks_encrypted(value: str) -> bool:
    """Best-effort: is this string a Fernet token? Used by tests and by
    one-off data-migration scripts that want to skip already-encrypted
    rows. Not relied on by the runtime path."""
    if not value or len(value) < 80:
        return False
    if not value.startswith("gAAAAA"):
        # Fernet tokens always start with the version byte (0x80) which
        # base64-encodes to ``gAAAAA``.
        return False
    try:
        _fernet().decrypt(value.encode("ascii"))
        return True
    except (InvalidToken, ValueError):
        return False


class EncryptedString(TypeDecorator[str]):
    """SQLAlchemy column type for at-rest-encrypted string columns.

    Usage::

        class User(Base):
            address: Mapped[str | None] = mapped_column(EncryptedString(200))

    The constructor's ``length`` argument is the **plaintext** max length
    you want to support; we pad the underlying VARCHAR generously so the
    Fernet ciphertext (~78 chars of overhead) fits with room to spare.

    Two important non-features:

    1. No padding / no deterministic encryption. Two writes of the same
       plaintext produce different ciphertexts. Don't put unique indexes
       on these columns; equality lookups on encrypted columns won't work.

    2. NULL passes through unchanged in both directions. We don't
       encrypt the absence of a value.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 200, **kwargs: Any) -> None:
        # ~78 chars Fernet overhead + base64 expansion of the
        # plaintext. ``length * 2 + 128`` is a comfortable upper bound
        # for anything up to ~500-char plaintexts. The Alembic
        # migration that introduces an encrypted column should
        # explicitly set the matching VARCHAR width on the DB side.
        super().__init__(length=length * 2 + 128, **kwargs)
        self._plaintext_length = length

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is None or value == "":
            return value
        return encrypt_value(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None or value == "":
            return value
        return decrypt_value(value)
