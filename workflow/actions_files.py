"""File system actions for reading and writing files."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from .flow import Step
from .runner import ExecutionContext


def file_read(step: Step, ctx: ExecutionContext) -> Any:
    path = Path(step.params["path"])
    mode = step.params.get("mode", "text")
    encoding = step.params.get("encoding", "utf-8")
    if mode == "binary":
        return path.read_bytes()
    return path.read_text(encoding)


def file_write(step: Step, ctx: ExecutionContext) -> Any:
    path = Path(step.params["path"])
    content = step.params.get("content", "")
    mode = step.params.get("mode", "text")
    encoding = step.params.get("encoding", "utf-8")
    if mode == "binary":
        data = content.encode(encoding) if isinstance(content, str) else content
        path.write_bytes(data)
    else:
        data = content.decode(encoding) if isinstance(content, bytes) else content
        path.write_text(data, encoding)
    return str(path)


def file_copy(step: Step, ctx: ExecutionContext) -> Any:
    src = Path(step.params["src"])
    dst = Path(step.params["dst"])
    shutil.copyfile(src, dst)
    return str(dst)


def file_move(step: Step, ctx: ExecutionContext) -> Any:
    src = Path(step.params["src"])
    dst = Path(step.params["dst"])
    shutil.move(src, dst)
    return str(dst)


def file_delete(step: Step, ctx: ExecutionContext) -> Any:
    path = Path(step.params["path"])
    path.unlink()
    return str(path)


FILES_ACTIONS = {
    "file.read": file_read,
    "file.write": file_write,
    "file.copy": file_copy,
    "file.move": file_move,
    "file.delete": file_delete,
}
