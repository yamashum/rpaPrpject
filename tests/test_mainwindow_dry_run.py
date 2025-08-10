import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import rpa_main_ui


class DummyRunner:
    def __init__(self) -> None:
        self.kwargs = None

    def run_flow(self, flow, inputs=None, path=None, *, auto_resume=False):  # pragma: no cover - simple stub
        self.kwargs = {
            "inputs": inputs,
            "path": path,
            "auto_resume": auto_resume,
        }
        return {"result": 123}


def test_on_dry_runs_flow_with_auto_resume_and_logs(monkeypatch):
    app = QApplication([])
    dummy = DummyRunner()
    monkeypatch.setattr(rpa_main_ui, "Runner", lambda: dummy)
    window = rpa_main_ui.MainWindow()
    window.on_dry()
    assert dummy.kwargs["auto_resume"]
    row = window.log_panel.table.rowCount() - 1
    assert window.log_panel.table.item(row, 2).text().endswith('Finished: {"result": 123}')
    window.close()
    app.quit()
