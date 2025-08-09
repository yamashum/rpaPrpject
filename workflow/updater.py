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
    version_file: PathLike,
    key: bytes,
) -> bool:
    """Check for an update and apply it if available.

    Parameters
    ----------
    version_url:
        URL returning the latest available version string.
    package_url:
        URL to the signed ZIP package for the latest version.
    install_dir:
        Directory where the package should be installed.
    version_file:
        Path to a file containing the currently installed version.  The file is
        updated on success and restored on failure which allows the version to
        be pinned between executions.
    key:
        Public key used to verify the package signature.

    The function fetches the latest version from ``version_url``.  When the
    version differs from the one stored in ``version_file`` a signed ZIP
    package is downloaded from ``package_url`` and verified using ``key``.  The
    current installation and version file are backed up before applying the
    update and restored if verification fails or any error occurs.
    """
    version_path = Path(version_file)
    current_version = (
        version_path.read_text().strip() if version_path.exists() else ""
    )
    latest = check_version(version_url)
    if latest == current_version:
        return False

    dest = Path(install_dir)
    backup = dest.with_suffix(dest.suffix + ".bak")
    version_backup = version_path.with_suffix(version_path.suffix + ".bak")

    if backup.exists():
        shutil.rmtree(backup)
    if dest.exists():
        dest.rename(backup)
    if version_path.exists():
        shutil.copy2(version_path, version_backup)

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
            version_path.write_text(latest)
    except Exception:
        if backup.exists():
            if dest.exists():
                shutil.rmtree(dest)
            backup.rename(dest)
        if version_backup.exists():
            if version_path.exists():
                version_path.unlink()
            version_backup.rename(version_path)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
        if version_backup.exists():
            version_backup.unlink()
    return True


__all__ = ["check_version", "apply_update"]
