"""Utilities to sign and verify flow packages."""
from __future__ import annotations

from pathlib import Path
from typing import Union
import hashlib
import hmac
import io
import zipfile

PathLike = Union[str, Path]


def _sig_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sig")


def _zip_bytes(path: Path) -> bytes:
    """Return deterministic ZIP archive bytes for the directory ``path``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(path.rglob("*")):
            if file.is_file():
                arcname = file.relative_to(path).as_posix()
                zinfo = zipfile.ZipInfo(arcname)
                # Normalise metadata to keep archive deterministic
                zinfo.date_time = (1980, 1, 1, 0, 0, 0)
                zinfo.external_attr = 0o644 << 16
                zf.writestr(zinfo, file.read_bytes())
    return buf.getvalue()


def sign_package(path: PathLike, key: bytes) -> str:
    """Create an HMAC-SHA256 signature for ``path`` using ``key``.

    ``path`` may point to a file or directory.  Directories are zipped in a
    deterministic manner prior to signing.  The signature is written alongside
    the target file with the same name plus a ``.sig`` suffix.  When a
    directory is provided, a ``.zip`` archive is created next to it and signed.
    The hexadecimal signature string is returned.
    """
    p = Path(path)
    if p.is_dir():
        data = _zip_bytes(p)
        p = p.with_suffix(p.suffix + ".zip")
        p.write_bytes(data)
    else:
        data = p.read_bytes()
    signature = hmac.new(key, data, hashlib.sha256).hexdigest()
    _sig_path(p).write_text(signature)
    return signature


def verify_package(path: PathLike, key: bytes) -> bool:
    """Verify the signature of ``path`` using ``key``.

    ``path`` may refer to either the original directory or the generated
    ``.zip`` archive.  Returns ``True`` when the signature matches, otherwise
    ``False``.
    """
    p = Path(path)
    if p.is_dir():
        p = p.with_suffix(p.suffix + ".zip")
    sig_file = _sig_path(p)
    if not sig_file.exists() or not p.exists():
        return False
    expected = sig_file.read_text().strip()
    actual = hmac.new(key, p.read_bytes(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, actual)


__all__ = ["sign_package", "verify_package"]
