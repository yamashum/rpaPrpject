from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
    QLabel,
    QTextEdit,
)


TEXT = {
    "title": "セレクタ編集",
    "desc": "対象要素を取得するためのセレクタを入力してください。",
    "selector_placeholder": "#main > div",
    "preview_placeholder": "指定したセレクタに一致する要素のプレビューがここに表示されます。",
    "preview_prefix": "プレビュー: {text}",
    "ok": "OK",
    "cancel": "キャンセル",
}


class SelectorEditorDialog(QDialog):
    """簡易プレビュー付きのセレクタ編集ダイアログ。"""

    def __init__(self, value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TEXT["title"])
        layout = QVBoxLayout(self)

        desc = QLabel(TEXT["desc"])
        layout.addWidget(desc)

        self._selector_edit = QLineEdit(value)
        self._selector_edit.setPlaceholderText(TEXT["selector_placeholder"])
        layout.addWidget(self._selector_edit)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(TEXT["preview_placeholder"])
        layout.addWidget(self._preview)

        self._selector_edit.textChanged.connect(self._update_preview)
        self._update_preview(self._selector_edit.text())

        btns = QHBoxLayout()
        ok_btn = QPushButton(TEXT["ok"])
        cancel_btn = QPushButton(TEXT["cancel"])
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _update_preview(self, text: str) -> None:
        """Update preview placeholder with the current selector."""
        text = text.strip()
        if text:
            self._preview.setPlainText(TEXT["preview_prefix"].format(text=text))
        else:
            self._preview.clear()

    @property
    def selector(self) -> str:
        """Return the edited selector string."""
        return self._selector_edit.text().strip()
