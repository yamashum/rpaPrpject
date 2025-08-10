from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
)


class SettingsDialog(QDialog):
    """Simple settings dialog allowing configuration of theme and timeout."""

    def __init__(self, config: Dict[str, object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        # Keep reference to original config so that we can update the caller
        self._orig_config = config
        # Work on a local copy until the user saves
        self._config: Dict[str, object] = dict(config)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Theme input
        self.theme_edit = QLineEdit()
        self.theme_edit.setText(str(self._config.get("theme", "light")))
        form.addRow("Theme", self.theme_edit)

        # Default timeout input
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 10_000_000)
        self.timeout_spin.setValue(int(self._config.get("default_timeout", 1000)))
        form.addRow("Default Timeout (ms)", self.timeout_spin)

        layout.addLayout(form)

        # Buttons
        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _save(self) -> None:
        """Persist settings to the configuration file and close the dialog."""
        self._config["theme"] = self.theme_edit.text().strip() or "light"
        self._config["default_timeout"] = self.timeout_spin.value()
        path = Path.home() / ".config" / "rpa_project" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._config, indent=2))
        # Reflect changes back to the original config dict
        self._orig_config.clear()
        self._orig_config.update(self._config)
        self.accept()
