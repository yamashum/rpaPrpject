from pathlib import Path

import pytest

from workflow.package_utils import sign_package
from workflow.updater import apply_update


def test_apply_update_invalid_signature_rolls_back(tmp_path: Path):
    # existing installation
    install = tmp_path / "app"
    install.mkdir()
    (install / "old.txt").write_text("old")

    # version information
    version_file = tmp_path / "version.txt"
    version_file.write_text("2.0")

    # new package with valid signature
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "new.txt").write_text("new")
    good_key = b"good"
    sign_package(pkg_dir, good_key)
    pkg_zip = pkg_dir.with_suffix(".zip")

    with pytest.raises(ValueError):
        apply_update(
            version_file.as_uri(),
            pkg_zip.as_uri(),
            install,
            current_version="1.0",
            key=b"bad",  # wrong key triggers verification failure
        )

    assert (install / "old.txt").read_text() == "old"
    assert not (install / "new.txt").exists()
