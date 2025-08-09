from pathlib import Path

from workflow.flow_signature import sign_flow, verify_flow


def test_sign_and_verify(tmp_path):
    flow_dir = tmp_path / "flow"
    flow_dir.mkdir()
    (flow_dir / "file.txt").write_text("data")
    key = b"secret"
    sig = sign_flow(flow_dir, key)
    assert sig
    zip_path = flow_dir.with_suffix(flow_dir.suffix + ".zip")
    assert zip_path.exists()
    assert verify_flow(zip_path, key)
