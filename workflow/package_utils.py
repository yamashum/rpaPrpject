"""Utilities to sign, verify and apply signed workflow packages."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union
import hashlib
import hmac
import io
import zipfile
import urllib.request
import tempfile
import shutil

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


def extract_package(path: PathLike, key: bytes, target: Optional[PathLike] = None) -> Path:
    """Extract a signed ZIP package after verifying its signature.

    Parameters
    ----------
    path:
        Path to the ``.zip`` package to extract.
    key:
        HMAC key used for signature verification.
    target:
        Optional directory to extract into.  When omitted a temporary
        directory is created and returned.

    Returns
    -------
    Path
        Directory containing the extracted package contents.

    Raises
    ------
    ValueError
        If signature verification fails.
    """

    p = Path(path)
    if not verify_package(p, key):
        raise ValueError("invalid package signature")

    if target is None:
        tmpdir = tempfile.mkdtemp()
        dest = Path(tmpdir)
    else:
        dest = Path(target)
        dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(p) as zf:
        zf.extractall(dest)
    return dest


def self_update(package_url: str, install_dir: PathLike, key: bytes) -> bool:
    """Download, verify and apply a signed package.

    ``package_url`` should point to the ``.zip`` archive.  A corresponding
    ``.sig`` file is fetched by appending ``.sig`` to the URL.  On successful
    verification the archive is extracted and its contents replace
    ``install_dir``.  The previous installation is kept in ``.bak`` for
    potential rollback.
    """

    with tempfile.TemporaryDirectory() as tmp:
        pkg_path = Path(tmp) / "update.zip"
        sig_path = _sig_path(pkg_path)

        with urllib.request.urlopen(package_url) as resp:
            pkg_path.write_bytes(resp.read())
        with urllib.request.urlopen(package_url + ".sig") as resp:
            sig_path.write_bytes(resp.read())

        if not verify_package(pkg_path, key):
            return False

        extract_dir = Path(tmp) / "extracted"
        with zipfile.ZipFile(pkg_path) as zf:
            zf.extractall(extract_dir)

        dest = Path(install_dir)
        backup = dest.with_suffix(dest.suffix + ".bak")
        if backup.exists():
            shutil.rmtree(backup)
        if dest.exists():
            dest.rename(backup)
        shutil.copytree(extract_dir, dest)
    return True


def rollback_update(install_dir: PathLike) -> bool:
    """Restore the previous installation if a backup exists."""
    dest = Path(install_dir)
    backup = dest.with_suffix(dest.suffix + ".bak")
    if not backup.exists():
        return False
    if dest.exists():
        shutil.rmtree(dest)
    backup.rename(dest)
    return True


__all__ = [
    "sign_package",
    "verify_package",
    "extract_package",
    "self_update",
    "rollback_update",
]
