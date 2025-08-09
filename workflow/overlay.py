from __future__ import annotations

from typing import Optional

try:  # pragma: no cover - optional dependency
    from PyQt6 import QtCore, QtWidgets  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    QtCore = QtWidgets = None  # type: ignore

from .runner import Runner


if QtWidgets is not None:  # pragma: no cover - GUI code
    class ControlOverlay(QtWidgets.QWidget):
        """Simple always-on-top overlay with pause/stop/skip controls."""

        def __init__(self, runner: Runner, parent: Optional[QtWidgets.QWidget] = None) -> None:
            super().__init__(parent)
            self.runner = runner
            self.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint
                | QtCore.Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
            layout = QtWidgets.QHBoxLayout(self)
            self.pause_btn = QtWidgets.QPushButton("Pause")
            self.stop_btn = QtWidgets.QPushButton("Stop")
            self.skip_btn = QtWidgets.QPushButton("Skip")
            layout.addWidget(self.pause_btn)
            layout.addWidget(self.stop_btn)
            layout.addWidget(self.skip_btn)
            self.pause_btn.clicked.connect(self._toggle_pause)
            self.stop_btn.clicked.connect(self.runner.stop)
            self.skip_btn.clicked.connect(self.runner.skip)

        def _toggle_pause(self) -> None:
            if self.runner.paused:
                self.runner.resume()
                self.pause_btn.setText("Pause")
            else:
                self.runner.pause()
                self.pause_btn.setText("Resume")
else:  # pragma: no cover - optional dependency
    class ControlOverlay:  # type: ignore
        """Fallback placeholder when PyQt6 is not available."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("PyQt6 is required for ControlOverlay")
