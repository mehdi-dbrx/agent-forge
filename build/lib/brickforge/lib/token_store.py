"""Token storage abstraction.

Tokens never touch disk as plaintext. Two backends:
- KeyringStore: OS keychain (local mode -- macOS/Windows/Linux desktop)
- SecretsStore: Databricks workspace secrets scope (Databricks Apps mode)

Usage:
    store = get_token_store()
    store.set("https://my-workspace.cloud.databricks.com", "dapi...")
    token = store.get("https://my-workspace.cloud.databricks.com")
    store.delete("https://my-workspace.cloud.databricks.com")
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

_log = logging.getLogger(__name__)
_SERVICE = "brickforge"


class TokenStore(ABC):
    @abstractmethod
    def get(self, host: str) -> str | None: ...
    @abstractmethod
    def set(self, host: str, token: str) -> None: ...
    @abstractmethod
    def delete(self, host: str) -> None: ...


class KeyringStore(TokenStore):
    """OS keychain via keyring library."""

    def __init__(self):
        import keyring
        self._kr = keyring

    def get(self, host: str) -> str | None:
        try:
            return self._kr.get_password(_SERVICE, host)
        except Exception as e:
            _log.warning("keyring get failed for %s: %s", host, e)
            return None

    def set(self, host: str, token: str) -> None:
        try:
            self._kr.set_password(_SERVICE, host, token)
        except Exception as e:
            _log.warning("keyring set failed for %s: %s", host, e)

    def delete(self, host: str) -> None:
        try:
            self._kr.delete_password(_SERVICE, host)
        except Exception as e:
            _log.warning("keyring delete failed for %s: %s", host, e)


class SecretsStore(TokenStore):
    """Databricks workspace secrets scope."""

    def __init__(self):
        from databricks.sdk import WorkspaceClient
        self._w = WorkspaceClient()
        self._scope = _SERVICE
        # Ensure scope exists
        try:
            self._w.secrets.create_scope(scope=self._scope)
        except Exception:
            pass  # already exists

    def _key(self, host: str) -> str:
        # Sanitize host URL to valid secret key name
        return host.replace("https://", "").replace("http://", "").replace("/", "").replace(".", "-")

    def get(self, host: str) -> str | None:
        try:
            resp = self._w.secrets.get_secret(scope=self._scope, key=self._key(host))
            if resp.value:
                import base64
                return base64.b64decode(resp.value).decode("utf-8")
            return None
        except Exception as e:
            _log.warning("secrets get failed for %s: %s", host, e)
            return None

    def set(self, host: str, token: str) -> None:
        try:
            self._w.secrets.put_secret(scope=self._scope, key=self._key(host), string_value=token)
        except Exception as e:
            _log.warning("secrets set failed for %s: %s", host, e)

    def delete(self, host: str) -> None:
        try:
            self._w.secrets.delete_secret(scope=self._scope, key=self._key(host))
        except Exception as e:
            _log.warning("secrets delete failed for %s: %s", host, e)


class NullStore(TokenStore):
    """Fallback when no backend is available. Tokens live in memory only."""

    def get(self, host: str) -> str | None:
        return None

    def set(self, host: str, token: str) -> None:
        pass

    def delete(self, host: str) -> None:
        pass


def get_token_store() -> TokenStore:
    """Return the appropriate token store for the current environment."""
    # Databricks Apps mode: use secrets scope
    if os.environ.get("DATABRICKS_APP_PORT"):
        try:
            return SecretsStore()
        except Exception as e:
            _log.warning("SecretsStore init failed, falling back: %s", e)

    # Local mode: use OS keychain
    try:
        return KeyringStore()
    except Exception as e:
        _log.warning("KeyringStore not available, tokens will not persist: %s", e)

    return NullStore()
