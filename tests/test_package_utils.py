from pathlib import Path
from workflow.package_utils import (
    extract_package,
    rollback_update,
    self_update,
    sign_package,
    verify_package,
)


def test_sign_and_verify(tmp_path: Path):
    pkg = tmp_path / "flow.pkg"
    pkg.write_text("data")
    key = b"secret"
    sign_package(pkg, key)
    assert verify_package(pkg, key) is True
    assert verify_package(pkg, b"wrong") is False


def test_extract_package(tmp_path: Path):
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "file.txt").write_text("ok")
    key = b"k"
    sign_package(src, key)
    zip_path = src.with_suffix(".zip")
    dest = extract_package(zip_path, key)
    assert (dest / "file.txt").read_text() == "ok"


def test_self_update_and_rollback(tmp_path: Path):
    # set up existing installation
    install = tmp_path / "app"
    install.mkdir()
    (install / "old.txt").write_text("old")

    # create new signed package
    new_pkg_dir = tmp_path / "new"
    new_pkg_dir.mkdir()
    (new_pkg_dir / "new.txt").write_text("new")
    key = b"secret"
    sign_package(new_pkg_dir, key)
    pkg_zip = new_pkg_dir.with_suffix(".zip")

    # use file:// URL for "download"
    url = pkg_zip.as_uri()
    assert self_update(url, install, key) is True
    assert (install / "new.txt").read_text() == "new"
    backup = install.with_suffix(".bak")
    assert (backup / "old.txt").read_text() == "old"

    # rollback
    assert rollback_update(install) is True
    assert (install / "old.txt").read_text() == "old"
