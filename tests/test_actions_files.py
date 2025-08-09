from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow.actions_files import file_read, file_write, file_copy, file_move, file_delete


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="t"), steps=[])
    return ExecutionContext(flow, {})


def test_file_actions(tmp_path):
    ctx = build_ctx()
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    moved = tmp_path / "moved.txt"
    file_write(Step(id="w", action="file.write", params={"path": str(src), "content": "hi"}), ctx)
    assert src.read_text() == "hi"
    content = file_read(Step(id="r", action="file.read", params={"path": str(src)}), ctx)
    assert content == "hi"
    file_copy(Step(id="c", action="file.copy", params={"src": str(src), "dst": str(dst)}), ctx)
    assert dst.read_text() == "hi"
    file_move(Step(id="m", action="file.move", params={"src": str(dst), "dst": str(moved)}), ctx)
    assert moved.read_text() == "hi"
    assert not dst.exists()
    file_delete(Step(id="d", action="file.delete", params={"path": str(moved)}), ctx)
    assert not moved.exists()
