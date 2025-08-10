import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

FLOWS_DIR = Path("flows")
APPROVAL_FILE = FLOWS_DIR / "approvals.json"

def _run_git(args: List[str]) -> str:
    """Run a git command and return its stdout."""
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()

def commit_and_tag(path: Path, message: str, tag: Optional[str] = None) -> str:
    """Commit ``path`` with ``message`` and optionally create ``tag``.

    Returns the commit hash of the new commit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["add", str(path)])
    try:
        _run_git(["commit", "-m", message, str(path)])
    except subprocess.CalledProcessError:
        # nothing to commit
        pass
    commit = _run_git(["log", "-n1", "--pretty=%H", "--", str(path)])
    if tag:
        try:
            _run_git(["tag", tag, commit])
        except subprocess.CalledProcessError:
            pass
    return commit

def history(path: Path, limit: int = 10) -> List[Tuple[str, str]]:
    """Return (commit, message) tuples for ``path``."""
    out = _run_git(["log", f"-n{limit}", "--pretty=%H %s", "--", str(path)])
    if not out:
        return []
    items = []
    for line in out.splitlines():
        if " " in line:
            commit, msg = line.split(" ", 1)
            items.append((commit, msg))
    return items

def diff(path: Path, commit_a: str, commit_b: str) -> str:
    return _run_git(["diff", commit_a, commit_b, "--", str(path)])

def mark_approved(commit: str) -> None:
    data = {}
    if APPROVAL_FILE.exists():
        try:
            data = json.loads(APPROVAL_FILE.read_text())
        except json.JSONDecodeError:
            data = {}
    data[commit] = True
    APPROVAL_FILE.write_text(json.dumps(data, indent=2))
    _run_git(["add", str(APPROVAL_FILE)])
    try:
        _run_git(["commit", "-m", f"approve {commit}", str(APPROVAL_FILE)])
    except subprocess.CalledProcessError:
        pass

def is_approved(path: Path) -> bool:
    if not path.is_relative_to(FLOWS_DIR):
        return True
    if not APPROVAL_FILE.exists():
        return False
    commit = _run_git(["log", "-n1", "--pretty=%H", "--", str(path)])
    try:
        data = json.loads(APPROVAL_FILE.read_text())
    except json.JSONDecodeError:
        return False
    return data.get(commit, False)
