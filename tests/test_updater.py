from pathlib import Path

import pytest

from workflow.package_utils import sign_package
from workflow.updater import apply_update


def _make_package(tmp_path: Path, filename: str = "new.txt") -> Path:
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / filename).write_text("new")
    sign_package(pkg_dir, b"good")
    return pkg_dir.with_suffix(".zip")


def test_apply_update_invalid_signature_rolls_back(tmp_path: Path):
    # existing installation
    install = tmp_path / "app"
    install.mkdir()
    (install / "old.txt").write_text("old")

    # remote version info
    remote_version = tmp_path / "remote_version.txt"
    remote_version.write_text("2.0")

    # local version file
    version_file = tmp_path / "current_version.txt"
    version_file.write_text("1.0")

    pkg_zip = _make_package(tmp_path)

    with pytest.raises(ValueError):
        apply_update(
            remote_version.as_uri(),
            pkg_zip.as_uri(),
            install,
            version_file,
            key=b"bad",  # wrong key triggers verification failure
        )

    assert (install / "old.txt").read_text() == "old"
    assert not (install / "new.txt").exists()
    assert version_file.read_text() == "1.0"


def test_apply_update_failure_restores_version_file(tmp_path: Path):
    install = tmp_path / "app"
    install.mkdir()
    (install / "old.txt").write_text("old")

    remote_version = tmp_path / "remote_version.txt"
    remote_version.write_text("2.0")

    version_file = tmp_path / "current_version.txt"
    version_file.write_text("1.0")

    pkg_zip = _make_package(tmp_path)

    with pytest.raises(ValueError):
        apply_update(
            remote_version.as_uri(),
            pkg_zip.as_uri(),
            install,
            version_file,
            key=b"bad",
        )

    assert version_file.read_text() == "1.0"
