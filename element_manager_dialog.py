from __future__ import annotations

import subprocess

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QLabel,
    QTabWidget,
    QMessageBox,
)
from workflow.gui_tools import ElementInfo, capture_coordinates, element_spy, spy_on_click
from workflow import element_store


TEXT = {
    "title": "要素取得・管理",
    "desc": "セレクタを指定して要素情報を取得し、一覧で管理します。",
    "selector_placeholder": "#main > div",
    "app_path_placeholder": "C:/path/to/app.exe",
    "spy_desktop": "デスクトップ取得",
    "spy_web": "WEB取得",
    "coord": "座標取得",
    "tab_desktop": "デスクトップ",
    "tab_web": "WEB",
    "tab_coord": "座標",
    "remove": "削除",
    "close": "閉じる",
    "column_selector": "セレクタ",
    "column_name": "Name",
    "column_auto": "AutomationId",
    "column_type": "ControlType",
    "column_class": "ClassName",
    "column_x": "X",
    "column_y": "Y",
}


class ElementManagerDialog(QDialog):
    """Simple dialog to capture and list element information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TEXT["title"])
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(TEXT["desc"]))

        self.app_path_edit = QLineEdit()
        self.app_path_edit.setPlaceholderText(TEXT["app_path_placeholder"])
        layout.addWidget(self.app_path_edit)

        form = QHBoxLayout()
        self.selector_edit = QLineEdit()
        self.selector_edit.setPlaceholderText(TEXT["selector_placeholder"])
        form.addWidget(self.selector_edit)
        self.spy_btn = QPushButton(TEXT["spy_desktop"])
        form.addWidget(self.spy_btn)
        self.web_btn = QPushButton(TEXT["spy_web"])
        form.addWidget(self.web_btn)
        self.coord_btn = QPushButton(TEXT["coord"])
        form.addWidget(self.coord_btn)
        layout.addLayout(form)

        self.tabs = QTabWidget()
        self.desktop_table = QTableWidget(0, 7)
        self.web_table = QTableWidget(0, 7)
        self.coord_table = QTableWidget(0, 7)
        for table in (self.desktop_table, self.web_table, self.coord_table):
            table.setHorizontalHeaderLabels(
                [
                    TEXT["column_selector"],
                    TEXT["column_name"],
                    TEXT["column_auto"],
                    TEXT["column_type"],
                    TEXT["column_class"],
                    TEXT["column_x"],
                    TEXT["column_y"],
                ]
            )
        self.tabs.addTab(self.desktop_table, TEXT["tab_desktop"])
        self.tabs.addTab(self.web_table, TEXT["tab_web"])
        self.tabs.addTab(self.coord_table, TEXT["tab_coord"])
        layout.addWidget(self.tabs)

        btns = QHBoxLayout()
        self.remove_btn = QPushButton(TEXT["remove"])
        self.close_btn = QPushButton(TEXT["close"])
        btns.addWidget(self.remove_btn)
        btns.addWidget(self.close_btn)
        layout.addLayout(btns)

        self.spy_btn.clicked.connect(self._on_spy)
        self.web_btn.clicked.connect(self._on_web_spy)
        self.coord_btn.clicked.connect(self._on_coord)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.close_btn.clicked.connect(self.accept)

    def _on_spy(self) -> None:
        app_path = self.app_path_edit.text().strip()
        if app_path:
            try:
                subprocess.Popen(app_path)
            except Exception as exc:
                QMessageBox.warning(self, TEXT["title"], str(exc))
        selector = self.selector_edit.text().strip()
        if selector:
            info = element_spy(selector)
            self.selector_edit.clear()
        else:
            info = spy_on_click()
        self._add_info(info, self.desktop_table)

    def _on_web_spy(self) -> None:
        selector = self.selector_edit.text().strip()
        if selector:
            info = element_spy(selector)
            self.selector_edit.clear()
        else:
            info = spy_on_click()
        self._add_info(info, self.web_table)

    def _on_coord(self) -> None:
        coords = capture_coordinates(wait=True)
        info = ElementInfo(
            selector=f"@{coords['x']},{coords['y']}",
            name=f"{coords['x']},{coords['y']}",
            x=coords["x"],
            y=coords["y"],
        )
        self._add_info(info, self.coord_table)

    def _add_info(self, info: ElementInfo, table: QTableWidget) -> None:
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(info.selector))
        table.setItem(row, 1, QTableWidgetItem(info.name or ""))
        table.setItem(row, 2, QTableWidgetItem(info.automation_id or ""))
        table.setItem(row, 3, QTableWidgetItem(info.control_type or ""))
        table.setItem(row, 4, QTableWidgetItem(info.class_name or ""))
        table.setItem(
            row,
            5,
            QTableWidgetItem(str(info.x) if info.x is not None else ""),
        )
        table.setItem(
            row,
            6,
            QTableWidgetItem(str(info.y) if info.y is not None else ""),
        )
        element_store.add_element(info)

    def _remove_selected(self) -> None:
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget):
            return
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        for row in rows:
            selector = table.item(row, 0).text()
            for info in element_store.list_elements():
                if info.selector == selector:
                    element_store.remove_element(info)
                    break
            table.removeRow(row)
