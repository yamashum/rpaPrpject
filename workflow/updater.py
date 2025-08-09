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
    from ``package_url`` and verified using ``key``.  The extracted contents are
    then copied over ``install_dir``.
    """
    latest = check_version(version_url)
    if latest == current_version:
        return False

    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "update.zip"
        sig = pkg.with_suffix(pkg.suffix + ".sig")
        with urllib.request.urlopen(package_url) as resp:
            pkg.write_bytes(resp.read())
        with urllib.request.urlopen(package_url + ".sig") as resp:
            sig.write_bytes(resp.read())
        if not verify_package(pkg, key):
            return False
        extract_dir = Path(tmp) / "extracted"
        with zipfile.ZipFile(pkg) as zf:
            zf.extractall(extract_dir)
        dest = Path(install_dir)
        for src in extract_dir.rglob("*"):
            dest_path = dest / src.relative_to(extract_dir)
            if src.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_path)
    return True


__all__ = ["check_version", "apply_update"]
