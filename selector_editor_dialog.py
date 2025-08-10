from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class SelectorEditorDialog(QDialog):
    """Simple dialog for editing a selector string."""

    def __init__(self, value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Selector Editor")
        layout = QVBoxLayout(self)

        self._edit = QLineEdit(value)
        layout.addWidget(self._edit)

        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    @property
    def selector(self) -> str:
        """Return the edited selector string."""
        return self._edit.text().strip()
