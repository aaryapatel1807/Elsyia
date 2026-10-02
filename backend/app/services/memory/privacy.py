"""Optional encryption for local memory content."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core import get_settings


class MemoryEncryptionError(RuntimeError):
    """Raised when encrypted memory cannot be read or configured."""


class MemoryCipher:
    """Fernet wrapper configured from the local environment."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise MemoryEncryptionError(
                "MEMORY_ENCRYPTION_KEY must be a valid Fernet key"
            ) from exc

    @classmethod
    def from_settings(cls) -> "MemoryCipher | None":
        key = get_settings().MEMORY_ENCRYPTION_KEY.strip()
        return cls(key) if key else None

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise MemoryEncryptionError(
                "Unable to decrypt memory; check MEMORY_ENCRYPTION_KEY"
            ) from exc
