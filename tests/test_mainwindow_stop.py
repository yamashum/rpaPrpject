import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import rpa_main_ui


class DummyRunner:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:  # pragma: no cover - simple flag setter
        self.stopped = True


def test_on_stop_requests_runner_and_logs():
    app = QApplication([])
    window = rpa_main_ui.MainWindow()
    dummy = DummyRunner()
    window.runner = dummy
    window.on_stop()
    assert dummy.stopped
    row = window.log_panel.table.rowCount() - 1
    assert window.log_panel.table.item(row, 2).text().endswith("Stop requested")
    window.close()
    app.quit()
