import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
import rpa_main_ui


def test_add_step_button(monkeypatch, tmp_path):
    monkeypatch.setattr(rpa_main_ui.Path, "home", lambda: tmp_path)
    app = QApplication([])
    window = rpa_main_ui.MainWindow()
    window.add_btn.click()
    assert len(window.flow.steps) > 0
    window.close()
    app.quit()
