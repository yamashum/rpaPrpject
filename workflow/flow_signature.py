"""Helpers to sign and verify workflow packages."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .package_utils import sign_package, verify_package

PathLike = Union[str, Path]


def sign_flow(path: PathLike, key: bytes) -> str:
    """Sign the workflow located at ``path``.

    Directories are zipped in a deterministic manner prior to signing.  The
    resulting ``.sig`` file is written alongside the target.  Returns the
    hexadecimal signature string.
    """
    return sign_package(path, key)


def verify_flow(path: PathLike, key: bytes) -> bool:
    """Verify the signature of the workflow at ``path``."""
    return verify_package(path, key)


__all__ = ["sign_flow", "verify_flow"]
