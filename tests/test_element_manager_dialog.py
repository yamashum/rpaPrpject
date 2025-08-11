import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from element_manager_dialog import ElementManagerDialog
from workflow.gui_tools import ElementInfo


def test_spy_adds_row(monkeypatch):
    app = QApplication.instance() or QApplication([])

    def fake_spy(selector: str) -> ElementInfo:
        return ElementInfo(selector=selector, name="n", automation_id="a", control_type="c", class_name="cls")

    monkeypatch.setattr("element_manager_dialog.element_spy", fake_spy)

    dlg = ElementManagerDialog()
    dlg.selector_edit.setText("#login")
    dlg._on_spy()
    assert dlg.desktop_table.rowCount() == 1
    dlg.tabs.setCurrentWidget(dlg.desktop_table)
    dlg.desktop_table.selectRow(0)
    dlg._remove_selected()
    assert dlg.desktop_table.rowCount() == 0


def test_spy_launches_app(monkeypatch):
    app = QApplication.instance() or QApplication([])

    launched = {}

    def fake_popen(path):
        launched["path"] = path

    monkeypatch.setattr("element_manager_dialog.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "element_manager_dialog.spy_on_click",
        lambda: ElementInfo(selector="@0,0", name="n", automation_id="a", control_type="c", class_name="cls"),
    )

    dlg = ElementManagerDialog()
    dlg.app_path_edit.setText("dummy.exe")
    dlg._on_spy()
    assert launched["path"] == "dummy.exe"
    assert dlg.desktop_table.rowCount() == 1
