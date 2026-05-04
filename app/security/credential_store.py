from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    class _FallbackKeyring:
        _bag: dict[tuple[str, str], str] = {}

        @classmethod
        def set_password(cls, service: str, account: str, password: str) -> None:
            cls._bag[(service, account)] = password

        @classmethod
        def get_password(cls, service: str, account: str) -> str | None:
            return cls._bag.get((service, account))

        @classmethod
        def delete_password(cls, service: str, account: str) -> None:
            cls._bag.pop((service, account), None)

    keyring = _FallbackKeyring()  # type: ignore


@dataclass
class CredentialRecord:
    email: str
    password: str


class KeyringCredentialStore:
    """Stores password in OS keyring and keeps only non-sensitive metadata on disk."""

    SERVICE_NAME = "auto_shop.buyma"
    ACCOUNT_KEY = "buyma_account"

    def __init__(self, metadata_path: str) -> None:
        self.metadata_path = metadata_path

    def save(self, email: str, password: str) -> None:
        os.makedirs(os.path.dirname(self.metadata_path), exist_ok=True)
        keyring.set_password(self.SERVICE_NAME, self.ACCOUNT_KEY, password)
        with open(self.metadata_path, "w", encoding="utf-8") as file:
            json.dump({"email": email.strip(), "storage": "keyring"}, file, ensure_ascii=False, indent=2)

    def load(self) -> Optional[CredentialRecord]:
        if not os.path.exists(self.metadata_path):
            return None
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            email = str(data.get("email", "")).strip()
            password = keyring.get_password(self.SERVICE_NAME, self.ACCOUNT_KEY) or ""
            if not email or not password:
                return None
            return CredentialRecord(email=email, password=password)
        except Exception:
            return None

    def load_email(self) -> str:
        record = self.load()
        return record.email if record else ""

    def exists(self) -> bool:
        return self.load() is not None


class KeyringTokenStore:
    """Stores a single secret token in the OS keyring."""

    def __init__(self, *, service_name: str, account_key: str) -> None:
        self.service_name = service_name
        self.account_key = account_key

    def save(self, token: str) -> None:
        token = (token or "").strip()
        if token:
            keyring.set_password(self.service_name, self.account_key, token)

    def delete(self) -> None:
        try:
            keyring.delete_password(self.service_name, self.account_key)
        except Exception:
            pass

    def load(self) -> str:
        try:
            return (keyring.get_password(self.service_name, self.account_key) or "").strip()
        except Exception:
            return ""

    def exists(self) -> bool:
        return bool(self.load())
