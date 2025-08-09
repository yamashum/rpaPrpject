"""Utilities for storing and retrieving secrets.

On Windows the credentials are stored using the Windows Credential Manager.
On other platforms a simple in-memory fallback store is used.  The fallback
is primarily intended for testing purposes.
"""
from __future__ import annotations

from typing import Optional, Dict
import sys

_fallback_store: Dict[str, str] = {}

if sys.platform == "win32":  # pragma: no cover - Windows specific
    try:
        import win32cred  # type: ignore
    except Exception:  # pragma: no cover - if pywin32 is missing
        win32cred = None
else:  # pragma: no cover - executed on non-Windows
    win32cred = None  # type: ignore


def set_secret(name: str, value: str) -> None:
    """Store ``value`` under ``name``.

    On Windows this writes to the Credential Manager.  On other platforms the
    value is kept in a process-local dictionary.
    """
    if win32cred:  # pragma: no cover - only executed on Windows
        credential = {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": name,
            "CredentialBlob": value.encode("utf-16"),
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }
        win32cred.CredWrite(credential, 0)
    else:
        _fallback_store[name] = value


def get_secret(name: str) -> Optional[str]:
    """Retrieve the secret stored under ``name``.

    Returns ``None`` when the secret does not exist.
    """
    if win32cred:  # pragma: no cover - only executed on Windows
        try:
            cred = win32cred.CredRead(name, win32cred.CRED_TYPE_GENERIC)
            return cred["CredentialBlob"].decode("utf-16")
        except Exception:
            return None
    return _fallback_store.get(name)


__all__ = ["set_secret", "get_secret"]
