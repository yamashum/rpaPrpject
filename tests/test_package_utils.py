from pathlib import Path
from workflow.package_utils import sign_package, verify_package


def test_sign_and_verify(tmp_path: Path):
    pkg = tmp_path / "flow.pkg"
    pkg.write_text("data")
    key = b"secret"
    sign_package(pkg, key)
    assert verify_package(pkg, key) is True
    assert verify_package(pkg, b"wrong") is False
