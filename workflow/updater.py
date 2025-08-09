"""Self-update utilities with version checks and signed packages."""
from __future__ import annotations

from pathlib import Path
from typing import Union
import urllib.request
import tempfile
import zipfile
import shutil

from .package_utils import verify_package

PathLike = Union[str, Path]


def check_version(version_url: str) -> str:
    """Fetch and return the latest version string from ``version_url``."""
    with urllib.request.urlopen(version_url) as resp:
        return resp.read().decode().strip()


def apply_update(
    version_url: str,
    package_url: str,
    install_dir: PathLike,
    current_version: str,
    key: bytes,
) -> bool:
    """Check for an update and apply it if available.

    The function fetches the latest version from ``version_url``.  When the
    version differs from ``current_version`` a signed ZIP package is downloaded
    from ``package_url`` and verified using ``key``.  The current installation
    is backed up before applying the update and restored if verification fails.
    """
    latest = check_version(version_url)
    if latest == current_version:
        return False

    dest = Path(install_dir)
    backup = dest.with_suffix(dest.suffix + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    if dest.exists():
        dest.rename(backup)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "update.zip"
            sig = pkg.with_suffix(pkg.suffix + ".sig")
            with urllib.request.urlopen(package_url) as resp:
                pkg.write_bytes(resp.read())
            with urllib.request.urlopen(package_url + ".sig") as resp:
                sig.write_bytes(resp.read())
            if not verify_package(pkg, key):
                raise ValueError("invalid package signature")
            extract_dir = Path(tmp) / "extracted"
            with zipfile.ZipFile(pkg) as zf:
                zf.extractall(extract_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(extract_dir, dest)
    except Exception:
        if backup.exists():
            if dest.exists():
                shutil.rmtree(dest)
            backup.rename(dest)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
    return True


__all__ = ["check_version", "apply_update"]
