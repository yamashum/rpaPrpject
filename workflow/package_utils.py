"""Utilities to sign and verify flow packages."""
from __future__ import annotations

from pathlib import Path
from typing import Union
import hashlib
import hmac

PathLike = Union[str, Path]


def _sig_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sig")


def sign_package(path: PathLike, key: bytes) -> str:
    """Create an HMAC-SHA256 signature for ``path`` using ``key``.

    The signature is written alongside the file with the same name plus a
    ``.sig`` suffix.  The hexadecimal signature string is also returned.
    """
    p = Path(path)
    data = p.read_bytes()
    signature = hmac.new(key, data, hashlib.sha256).hexdigest()
    _sig_path(p).write_text(signature)
    return signature


def verify_package(path: PathLike, key: bytes) -> bool:
    """Verify the signature of ``path`` using ``key``.

    Returns ``True`` when the signature matches, otherwise ``False``.
    """
    p = Path(path)
    sig_file = _sig_path(p)
    if not sig_file.exists():
        return False
    expected = sig_file.read_text().strip()
    actual = hmac.new(key, p.read_bytes(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, actual)


__all__ = ["sign_package", "verify_package"]
