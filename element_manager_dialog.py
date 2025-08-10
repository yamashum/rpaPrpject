from __future__ import annotations

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
)
from workflow.gui_tools import ElementInfo, capture_coordinates, element_spy
from workflow import element_store


TEXT = {
    "title": "要素取得・管理",
    "desc": "セレクタを指定して要素情報を取得し、一覧で管理します。",
    "selector_placeholder": "#main > div",
    "spy": "取得",
    "coord": "座標取得",
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

        form = QHBoxLayout()
        self.selector_edit = QLineEdit()
        self.selector_edit.setPlaceholderText(TEXT["selector_placeholder"])
        form.addWidget(self.selector_edit)
        self.spy_btn = QPushButton(TEXT["spy"])
        form.addWidget(self.spy_btn)
        self.coord_btn = QPushButton(TEXT["coord"])
        form.addWidget(self.coord_btn)
        layout.addLayout(form)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
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
        layout.addWidget(self.table)

        btns = QHBoxLayout()
        self.remove_btn = QPushButton(TEXT["remove"])
        self.close_btn = QPushButton(TEXT["close"])
        btns.addWidget(self.remove_btn)
        btns.addWidget(self.close_btn)
        layout.addLayout(btns)

        self.spy_btn.clicked.connect(self._on_spy)
        self.coord_btn.clicked.connect(self._on_coord)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.close_btn.clicked.connect(self.accept)

    def _on_spy(self) -> None:
        selector = self.selector_edit.text().strip()
        if not selector:
            return
        info = element_spy(selector)
        self._add_info(info)
        self.selector_edit.clear()

    def _on_coord(self) -> None:
        coords = capture_coordinates()
        info = ElementInfo(
            selector=f"@{coords['x']},{coords['y']}",
            name=f"{coords['x']},{coords['y']}",
            x=coords["x"],
            y=coords["y"],
        )
        self._add_info(info)

    def _add_info(self, info: ElementInfo) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(info.selector))
        self.table.setItem(row, 1, QTableWidgetItem(info.name or ""))
        self.table.setItem(row, 2, QTableWidgetItem(info.automation_id or ""))
        self.table.setItem(row, 3, QTableWidgetItem(info.control_type or ""))
        self.table.setItem(row, 4, QTableWidgetItem(info.class_name or ""))
        self.table.setItem(row, 5, QTableWidgetItem(str(info.x) if info.x is not None else ""))
        self.table.setItem(row, 6, QTableWidgetItem(str(info.y) if info.y is not None else ""))
        element_store.add_element(info)

    def _remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            selector = self.table.item(row, 0).text()
            for info in element_store.list_elements():
                if info.selector == selector:
                    element_store.remove_element(info)
                    break
            self.table.removeRow(row)
