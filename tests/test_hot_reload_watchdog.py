import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import rpa_main_ui


def test_watchdog_triggers_reload():
    event = threading.Event()

    def fake_on_flow_updated(self, path):
        event.set()

    original = rpa_main_ui.MainWindow.on_flow_updated
    rpa_main_ui.MainWindow.on_flow_updated = fake_on_flow_updated
    try:
        app = QApplication([])
        window = rpa_main_ui.MainWindow()
        # allow observer to start
        time.sleep(0.5)
        p = Path("sample_flow.json")
        p.write_text(p.read_text() + "\n")
        assert event.wait(5), "watchdog did not trigger"
        window.close()
        app.quit()
    finally:
        rpa_main_ui.MainWindow.on_flow_updated = original

