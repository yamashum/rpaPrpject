import os
import sys
import json
import copy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import queue
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QMimeData
from PyQt6.QtGui import (
    QFont,
    QPainter,
    QColor,
    QPen,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QScrollArea,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QWizard,
    QWizardPage,
    QPlainTextEdit,
    QMessageBox,
    QMenu,
)
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from workflow.flow_git import commit_and_tag, history as flow_history, diff as flow_diff, mark_approved
from workflow.flow import Flow, Step, Meta
from workflow.runner import Runner
from workflow.logging import set_step_log_callback
from workflow.actions import list_actions
from settings_dialog import SettingsDialog
from selector_editor_dialog import SelectorEditorDialog

# Global queue receiving actions recorded by external modules
recorded_actions_q: "queue.Queue[dict]" = queue.Queue()


TEXT = {
    "wizard_title": "はじめに",
    "wizard_create_flow": "フローを作成",
    "wizard_create_flow_desc": "アクションパレットを使って必要なステップを追加し、フローを構築します。",
    "wizard_run_flow": "フローを実行",
    "wizard_run_flow_desc": "「実行」ボタンでフローを実行し、「ドライラン」で副作用なくテストできます。",
    "action_palette": "アクションパレット",
    "properties": "プロパティ",
    "param_message": "メッセージ",
    "param_variable": "変数",
    "param_value": "値",
    "param_milliseconds": "ミリ秒",
    "param_default": "既定値",
    "param_mask": "入力を隠す",
    "param_options": "選択肢",
    "label_action": "アクション",
    "label_selector_editor": "セレクタ編集",
    "label_output_variable": "出力変数",
    "label_timeout": "タイムアウト",
    "label_retry": "再試行回数",
    "label_on_failure": "失敗時",
    "checkbox_save_screenshot": "スクリーンショットを保存",
    "tooltip_run": "現在のワークフローを実行します",
    "tooltip_stop": "実行中のワークフローを停止します",
    "tooltip_dry": "副作用なしでワークフローを実行します",
    "tooltip_settings": "設定を開きます",
    "tooltip_history": "実行履歴を表示します",
    "tooltip_approval": "このフローの承認を依頼します",
    "log_header_time": "時刻",
    "log_header_step": "ステップ",
    "log_header_status": "状態",
    "history_title": "フロー履歴",
    "history_commit": "コミット",
    "history_message": "メッセージ",
    "approval_request": "承認依頼",
    "approval_failed": "失敗: {exc}",
    "approval_sent": "送信しました",
    "main_title": "RPAデザイナーモック",
    "action_click": "クリック",
    "action_input": "入力",
    "action_write_excel": "Excelに書き込み",
    "action_web_navigate": "Web - 移動",
    "action_new_step": "新しいステップ",
}


class FlowChangeHandler(FileSystemEventHandler, QObject):
    """Bridge watchdog events to Qt signals."""

    file_changed = pyqtSignal(str)

    def __init__(self) -> None:
        FileSystemEventHandler.__init__(self)
        QObject.__init__(self)

    def _handle(self, path: str) -> None:
        if path.endswith(".json") or path.endswith(".py"):
            self.file_changed.emit(path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

# ---------- Onboarding Wizard ----------
class OnboardingWizard(QWizard):
    """初回起動時に表示される簡単な導入ウィザード。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TEXT["wizard_title"])

        # Page 1 - flow creation
        page1 = QWizardPage()
        page1.setTitle(TEXT["wizard_create_flow"])
        l1 = QVBoxLayout()
        label1 = QLabel(TEXT["wizard_create_flow_desc"])
        label1.setWordWrap(True)
        l1.addWidget(label1)
        page1.setLayout(l1)

        # Page 2 - execution
        page2 = QWizardPage()
        page2.setTitle(TEXT["wizard_run_flow"])
        l2 = QVBoxLayout()
        label2 = QLabel(TEXT["wizard_run_flow_desc"])
        label2.setWordWrap(True)
        l2.addWidget(label2)
        page2.setLayout(l2)

        self.addPage(page1)
        self.addPage(page2)

# ---------- 中央キャンバス（ドット背景＋カード） ----------
class StepListWidget(QListWidget):
    """List widget that supports internal drag & drop to reorder steps."""

    orderChanged = pyqtSignal()
    stepSelected = pyqtSignal(Step)

    def __init__(self):
        super().__init__()
        # Allow both internal moves and external drops
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSpacing(18)
        self.setStyleSheet("QListWidget{background:transparent;border:none;}")
        self.currentItemChanged.connect(self._on_current_item_changed)

    def _on_current_item_changed(self, current, previous):
        if not current:
            return
        step = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(step, Step):
            self.stepSelected.emit(step)

    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.source() is self:
            event.setDropAction(Qt.DropAction.MoveAction)
            super().dragEnterEvent(event)
        elif event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # type: ignore[override]
        if event.source() is self:
            event.setDropAction(Qt.DropAction.MoveAction)
            super().dragMoveEvent(event)
        elif event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):  # type: ignore[override]
        if event.source() is self:
            event.setDropAction(Qt.DropAction.MoveAction)
            super().dropEvent(event)
            self.orderChanged.emit()
        elif event.mimeData().hasText():
            action = event.mimeData().text().strip()
            mw = self.window()
            if hasattr(mw, "add_step"):
                row = self.indexAt(event.position().toPoint()).row()
                index = row if row >= 0 else None
                mw.add_step(action=action, index=index)
            event.acceptProposedAction()
        else:
            event.ignore()


class DottedCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color:#FAFBFE;")
        self.setAcceptDrops(True)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(40, 24, 40, 24)
        self.v.setSpacing(18)
        self.v.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.list = StepListWidget()
        self.v.addWidget(self.list)

    def paintEvent(self, e):  # type: ignore[override]
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(QColor("#E9EDF6"), 1))
        step = 16
        for y in range(0, self.height(), step):
            for x in range(0, self.width(), step):
                p.drawPoint(x, y)
        p.end()

    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasText():
            action = event.mimeData().text().strip()
            mw = self.window()
            if hasattr(mw, "add_step"):
                mw.add_step(action=action)
            event.acceptProposedAction()
        else:
            event.ignore()

class StepCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, icon, title, subtitle):
        super().__init__()
        self.setObjectName("stepCard")
        self.setFixedSize(380, 82)
        self.setStyleSheet("""
            QFrame#stepCard { background:#fff; border:1px solid #E5EAF5; border-radius:12px; }
            QFrame#stepCard:hover { border:1px solid #B8C6E6; }
            QLabel#icon { background:#EEF3FF; border:1px solid #E0E8FF; border-radius:8px; font-size:20px; }
            QLabel.title { color:#1F2A44; font-weight:700; }
            QLabel.sub   { color:#6B7A99; }
        """)
        h = QHBoxLayout(self); h.setContentsMargins(14, 12, 14, 12); h.setSpacing(12)
        ic = QLabel(icon); ic.setObjectName("icon"); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setFixedSize(40, 40)
        texts = QVBoxLayout()
        t = QLabel(title); t.setObjectName("title"); t.setFont(QFont("", 11))
        s = QLabel(subtitle); s.setObjectName("sub");  s.setFont(QFont("", 10))
        texts.addWidget(t); texts.addWidget(s)
        self.more = QPushButton("⋯")
        self.more.setFixedSize(28, 28)
        self.more.setStyleSheet(
            "QPushButton{background:#fff;border:1px solid #E5EAF5;border-radius:14px;color:#6B7A99;font-size:16px;} QPushButton:hover{background:#F6F8FD;}"
        )
        h.addWidget(ic); h.addLayout(texts); h.addStretch(1); h.addWidget(self.more)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

def add_step_button():
    btn = QPushButton("＋ ステップ追加")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(160, 36)
    btn.setStyleSheet("""
        QPushButton{background:#fff;color:#3C4B69;border:1px dashed #C9D3E6;border-radius:8px;font-weight:600;}
        QPushButton:hover{background:#F6F8FD;}
    """)
    return btn

# ---------- 左パレット ----------
class _PaletteListWidget(QListWidget):
    """List widget for the action palette that provides drag support."""

    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)

    def mimeData(self, items):  # type: ignore[override]
        mime = QMimeData()
        if items:
            item = items[0]
            if not item.font().bold():
                mime.setText(item.text().strip())
        return mime

class ActionPalette(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("leftPanel")
        self.setMinimumWidth(260)
        self.setStyleSheet("""
            QWidget#leftPanel{ background:#fff; border-right:1px solid #E5EAF5; }
            QLabel.title{ color:#1F2A44; font-weight:700; font-size:14px; }
            QListWidget{ border:none; padding:0 8px 12px 8px; color:#4A5878; }
            QListWidget::item{ padding:6px 4px; }
            QListWidget::item:selected{ background:#EEF3FF; color:#1F2A44; border-radius:6px; }
        """)
        v = QVBoxLayout(self); v.setContentsMargins(16,16,16,16); v.setSpacing(10)
        title = QLabel(TEXT["action_palette"]); title.setObjectName("title")
        self.list = _PaletteListWidget()
        v.addWidget(title); v.addWidget(self.list)
        self._adv_items: list[QListWidgetItem] = []
        for header, items in list_actions().items():
            display = [self._humanize(a) for a in items]
            self._section(header, display, advanced=header == "詳細設定")

    def _section(self, header, items, *, advanced: bool = False):
        h = QListWidgetItem(f"  {header}"); f = QFont(); f.setBold(True); h.setFont(f)
        self.list.addItem(h)
        targets = [h]
        for it in items:
            item = QListWidgetItem(f"    {it}")
            self.list.addItem(item)
            targets.append(item)
        if advanced:
            self._adv_items.extend(targets)

    def set_advanced_visible(self, visible: bool) -> None:
        for item in self._adv_items:
            item.setHidden(not visible)

    @staticmethod
    def _humanize(name: str) -> str:
        """Convert internal action names to human readable labels."""
        return name.replace("_", " ").replace(".", " / ").title()

# ---------- 右プロパティ ----------
class PropertiesPanel(QWidget):
    """Panel showing editable properties for the selected step.

    The panel dynamically builds a small form based on the step action.  Each
    action can define its own parameters and whether common fields like the
    selector should be displayed.  Only a handful of basic actions are
    supported here but the structure allows easy extension in the future.
    """

    # form specifications for individual actions
    ACTION_FORMS: dict[str, dict[str, object]] = {
        "log": {
            "selector": False,
            "params": [("message", QLineEdit, TEXT["param_message"], {})],
        },
        "set": {
            "selector": False,
            "params": [
                ("name", QLineEdit, TEXT["param_variable"], {}),
                ("value", QLineEdit, TEXT["param_value"], {}),
            ],
        },
        "wait": {
            "selector": False,
            "params": [
                ("ms", QSpinBox, TEXT["param_milliseconds"], {"min": 0, "max": 120000, "suffix": " ms"}),
            ],
        },
        "prompt.input": {
            "selector": False,
            "params": [
                ("message", QLineEdit, TEXT["param_message"], {}),
                ("default", QLineEdit, TEXT["param_default"], {}),
                ("mask", QCheckBox, TEXT["param_mask"], {}),
            ],
        },
        "prompt.confirm": {
            "selector": False,
            "params": [
                ("message", QLineEdit, TEXT["param_message"], {}),
                ("default", QComboBox, TEXT["param_default"], {"items": ["True", "False", "None"]}),
            ],
        },
        "prompt.select": {
            "selector": False,
            "params": [
                ("message", QLineEdit, TEXT["param_message"], {}),
                ("options", QLineEdit, TEXT["param_options"], {"list": True}),
                ("default", QLineEdit, TEXT["param_default"], {}),
            ],
        },
    }

    def __init__(self):
        super().__init__()
        self.setObjectName("propPanel")
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            QWidget#propPanel{ background:#fff; border-left:1px solid #E5EAF5; }
            QLabel.header{ color:#1F2A44; font-weight:700; font-size:16px; }
            QLineEdit, QComboBox{ background:#fff; border:1px solid #DCE3F2; border-radius:8px; padding:6px 8px; }
            QSpinBox{ background:#fff; border:1px solid #DCE3F2; border-radius:8px; padding:4px 8px; }
        """)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)
        head = QLabel(TEXT["properties"])
        head.setObjectName("header")
        v.addWidget(head)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.act = QComboBox()
        self.act.addItems(
            [
                TEXT["action_click"],
                TEXT["action_input"],
                TEXT["action_write_excel"],
                TEXT["action_web_navigate"],
            ]
        )
        self.selector = QLineEdit("any01   UIA/image...")
        self.out = QLineEdit("result1")
        self.to = QSpinBox()
        self.to.setRange(0, 120000)
        self.to.setValue(3000)
        self.to.setSuffix(" ms")
        self.re = QSpinBox()
        self.re.setRange(0, 20)
        self.re.setValue(3)
        self.chk = QCheckBox(TEXT["checkbox_save_screenshot"])
        self.chk.setChecked(True)
        form.addRow(TEXT["label_action"], self.act)
        self.selector_btn = QPushButton("開く…")
        self.selector_btn.clicked.connect(self._open_selector_editor)
        form.addRow(TEXT["label_selector_editor"], self.selector_btn)
        form.addRow(self.selector)
        v.addLayout(form)

        # dynamic parameter form
        self.param_form = QFormLayout()
        self.param_form.setHorizontalSpacing(12)
        self.param_form.setVerticalSpacing(10)
        v.addLayout(self.param_form)
        self.param_fields: dict[str, QWidget] = {}
        self._field_specs: dict[str, tuple] = {}

        self.advanced_group = QWidget()
        adv_v = QVBoxLayout(self.advanced_group)
        adv_v.setContentsMargins(0, 0, 0, 0)
        adv_v.setSpacing(10)
        adv_form = QFormLayout()
        adv_form.setHorizontalSpacing(12)
        adv_form.setVerticalSpacing(10)
        adv_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        adv_form.addRow(TEXT["label_output_variable"], self.out)
        adv_form.addRow(TEXT["label_timeout"], self.to)
        adv_form.addRow(TEXT["label_retry"], self.re)
        adv_v.addLayout(adv_form)
        adv_v.addWidget(QLabel(TEXT["label_on_failure"]))
        adv_v.addWidget(self.chk)
        v.addWidget(self.advanced_group)
        v.addStretch(1)

        self._current_step: Step | None = None
        self._loading = False

        self.act.currentIndexChanged.connect(self._on_action_changed)
        self.selector.editingFinished.connect(self._on_changed)
        self.out.editingFinished.connect(self._on_changed)
        self.to.valueChanged.connect(self._on_changed)
        self.re.valueChanged.connect(self._on_changed)
        self.chk.toggled.connect(self._on_changed)
        self._selector_label = form.labelForField(self.selector_btn)

    def _open_selector_editor(self) -> None:
        """Open a dialog for editing the selector value."""
        dlg = SelectorEditorDialog(self.selector.text(), self)
        if dlg.exec():
            self.selector.setText(dlg.selector)
            self._on_changed()

    def set_advanced_visible(self, visible: bool) -> None:
        self.advanced_group.setVisible(visible)

    def load_step(self, step: Step) -> None:
        """Populate the form fields from ``step``."""
        self._current_step = step
        self._loading = True
        self.act.setCurrentText(step.action or "")
        # build parameter widgets for this action
        self._build_action_form(step.action or "")
        if step.selector and isinstance(step.selector, dict):
            self.selector.setText(str(step.selector.get("value", "")))
        else:
            self.selector.setText("")
        self.out.setText(step.out or "")
        self.to.setValue(step.timeoutMs or 0)
        self.re.setValue(step.retry or 0)
        self.chk.setChecked(step.onError.get("screenshot", False))
        # populate action-specific params
        for name, widget in self.param_fields.items():
            val = step.params.get(name)
            if isinstance(widget, QLineEdit):
                widget.setText("" if val is None else str(val))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(val) if val is not None else 0)
            elif isinstance(widget, QComboBox):
                text = "" if val is None else str(val)
                idx = widget.findText(text)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))
        self._loading = False
        self.update()

    def apply_changes(self, step: Step) -> None:
        """Write form values back to ``step``."""
        step.action = self.act.currentText() or None
        selector_txt = self.selector.text().strip()
        step.selector = {"value": selector_txt} if selector_txt else None
        out_txt = self.out.text().strip()
        step.out = out_txt or None
        step.timeoutMs = self.to.value() or None
        step.retry = self.re.value() or None
        step.onError["screenshot"] = self.chk.isChecked()
        # write action specific params
        for name, widget in self.param_fields.items():
            spec = self._field_specs.get(name, {})
            if isinstance(widget, QLineEdit):
                txt = widget.text().strip()
                if spec.get("list"):
                    step.params[name] = [t.strip() for t in txt.split(",") if t.strip()]
                elif txt:
                    step.params[name] = txt
                else:
                    step.params.pop(name, None)
            elif isinstance(widget, QSpinBox):
                step.params[name] = widget.value()
            elif isinstance(widget, QComboBox):
                val = widget.currentText()
                if val == "True":
                    step.params[name] = True
                elif val == "False":
                    step.params[name] = False
                elif val == "None" or val == "":
                    step.params.pop(name, None)
                else:
                    step.params[name] = val
            elif isinstance(widget, QCheckBox):
                step.params[name] = widget.isChecked()

    def _build_action_form(self, action: str) -> None:
        """(Re)build the form for the given action."""
        # remove previous widgets
        while self.param_form.count():
            item = self.param_form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.param_fields.clear()
        self._field_specs.clear()

        cfg = self.ACTION_FORMS.get(action)
        needs_selector = True
        if cfg:
            needs_selector = cfg.get("selector", True)
            for name, widget_cls, label, extra in cfg.get("params", []):
                widget: QWidget = widget_cls()
                # apply extra options
                if isinstance(widget, QSpinBox):
                    widget.setRange(extra.get("min", 0), extra.get("max", 999999))
                    if "suffix" in extra:
                        widget.setSuffix(extra["suffix"])
                if isinstance(widget, QComboBox) and "items" in extra:
                    widget.addItems(list(extra["items"]))
                self.param_form.addRow(label, widget)
                self.param_fields[name] = widget
                self._field_specs[name] = extra
                # connect change signals
                if isinstance(widget, QLineEdit):
                    widget.editingFinished.connect(self._on_changed)
                elif isinstance(widget, QSpinBox):
                    widget.valueChanged.connect(self._on_changed)
                elif isinstance(widget, QComboBox):
                    widget.currentIndexChanged.connect(self._on_changed)
                elif isinstance(widget, QCheckBox):
                    widget.toggled.connect(self._on_changed)
        # show/hide selector row
        self.selector.setVisible(needs_selector)
        self.selector_btn.setVisible(needs_selector)
        if self._selector_label:
            self._selector_label.setVisible(needs_selector)

    def _on_action_changed(self, idx: int) -> None:
        if self._loading:
            return
        self._build_action_form(self.act.currentText())
        self._on_changed()

    def _on_changed(self, *args) -> None:
        if self._loading or not self._current_step:
            return
        mw = self.window()
        if hasattr(mw, "record_history"):
            mw.record_history()
        self.apply_changes(self._current_step)
        # update card subtitle
        if hasattr(mw, "canvas"):
            item = mw.canvas.list.currentItem()
            if item:
                card = mw.canvas.list.itemWidget(item)
                if card:
                    sub = card.findChild(QLabel, "sub")
                    if sub:
                        sub.setText(self._current_step.action or "")
        if hasattr(mw, "save_flow"):
            mw.save_flow()

# ---------- ヘッダー ----------
class HeaderBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("headerBar")
        self.setStyleSheet("""
            QWidget#headerBar{ background:#fff; border-bottom:1px solid #E5EAF5; }
            QPushButton#primary{ background:#2D68FF; color:#fff; border-radius:8px; padding:7px 16px; font-weight:700; }
            QPushButton#primary:hover{ background:#1F55E6; }
            QPushButton.ghost{ background:#fff; color:#34446A; border:1px solid #DCE3F2; border-radius:8px; padding:7px 16px; font-weight:600; }
            QPushButton.ghost:hover{ background:#F6F8FD; }
        """)
        h = QHBoxLayout(self); h.setContentsMargins(16,10,16,10); h.setSpacing(10)
        self.run_btn = QPushButton("▶ 実行"); self.run_btn.setObjectName("primary")
        self.stop_btn = QPushButton("□ 停止"); self.stop_btn.setProperty("class","ghost")
        self.dry_btn  = QPushButton("◻ ドライラン"); self.dry_btn.setProperty("class","ghost")
        self.sett_btn = QPushButton("⚙ 設定"); self.sett_btn.setProperty("class","ghost")
        self.hist_btn = QPushButton("履歴"); self.hist_btn.setProperty("class","ghost")
        self.appr_btn = QPushButton("承認依頼"); self.appr_btn.setProperty("class","ghost")
        self.adv_chk = QCheckBox("詳細設定"); self.adv_chk.setProperty("class","ghost")

        # basic context help so first-time users understand the actions
        self.run_btn.setToolTip(TEXT["tooltip_run"])
        self.stop_btn.setToolTip(TEXT["tooltip_stop"])
        self.dry_btn.setToolTip(TEXT["tooltip_dry"])
        self.sett_btn.setToolTip(TEXT["tooltip_settings"])
        self.hist_btn.setToolTip(TEXT["tooltip_history"])
        self.appr_btn.setToolTip(TEXT["tooltip_approval"])
        left = QHBoxLayout(); left.setSpacing(8)
        left.addWidget(self.run_btn); left.addWidget(self.stop_btn); left.addWidget(self.dry_btn); left.addWidget(self.sett_btn)
        left.addWidget(self.hist_btn); left.addWidget(self.appr_btn); left.addWidget(self.adv_chk)
        h.addLayout(left); h.addStretch(1)
        user = QLabel("🔍    👤"); user.setStyleSheet("color:#8AA0C6;")
        h.addWidget(user)

# ---------- ログ（💥ここを修正） ----------
class LogPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("logPanel")
        self.setStyleSheet("""
            QFrame#logPanel { background:#FFFFFF; border-top:1px solid #E5EAF5; }
            QTableWidget { background:#FFFFFF; border:none; }
            QHeaderView::section { background:#FFFFFF; color:#6B7A99; border:none; padding:8px; }
            QTableWidget::item { padding:8px; }
        """)
        v = QVBoxLayout(self); v.setContentsMargins(12,8,12,8); v.setSpacing(6)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            TEXT["log_header_time"],
            TEXT["log_header_step"],
            TEXT["log_header_status"],
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # 列幅とヘッダ挙動
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        v.addWidget(self.table)

    def add_row(self, t, step, status_text, ok=True):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(t))
        self.table.setItem(r, 1, QTableWidgetItem(step))
        st = QTableWidgetItem(("✅  " if ok else "❌  ") + status_text)
        # color-code status for quick visual feedback
        st.setForeground(QColor("#1F9651" if ok else "#E74C3C"))
        self.table.setItem(r, 2, st)
        self.table.setRowHeight(r, 26)
        # always show the latest log entry
        self.table.scrollToBottom()

# Bridge log_step callbacks into the UI thread
class _StepLogBridge(QObject):
    """Routes step log records to the :class:`LogPanel` on the GUI thread."""

    step_logged = pyqtSignal(dict)

    def __init__(self, panel: LogPanel) -> None:
        super().__init__()
        self._panel = panel
        self.step_logged.connect(self._handle)

    def _handle(self, record: dict) -> None:
        t = datetime.now().strftime("%H:%M:%S")
        step = f"{record.get('stepId')} {record.get('action')}"
        status = record.get("result", "")
        ok = status in {"ok", "skipped"}
        self._panel.add_row(t, step, status, ok=ok)

# ---------- 履歴ダイアログ ----------
class FlowHistoryDialog(QDialog):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.setWindowTitle(TEXT["history_title"])
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([
            TEXT["history_commit"],
            TEXT["history_message"],
        ])
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        self.commits: list[str] = []
        for commit, msg in flow_history(path, 20):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(commit[:7]))
            self.table.setItem(row, 1, QTableWidgetItem(msg))
            self.commits.append(commit)
        self.diff_view = QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        layout.addWidget(self.diff_view)
        btns = QHBoxLayout()
        diff_btn = QPushButton("差分表示")
        approve_btn = QPushButton("承認")
        diff_btn.clicked.connect(self._show_diff)
        approve_btn.clicked.connect(self._approve)
        btns.addWidget(diff_btn)
        btns.addWidget(approve_btn)
        layout.addLayout(btns)

    def _selected_commit(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.commits[row]

    def _show_diff(self) -> None:
        commit = self._selected_commit()
        if not commit:
            return
        text = flow_diff(self.path, f"{commit}^", commit)
        self.diff_view.setPlainText(text)

    def _approve(self) -> None:
        commit = self._selected_commit()
        if not commit:
            return
        flow = Flow.from_dict(json.loads(self.path.read_text()))
        Runner().approve_flow(flow)
        mark_approved(commit)
        self.accept()

# ---------- メイン ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TEXT["main_title"])
        self.resize(1280, 860)
        self.current_flow_path = Path("flows/sample_flow.json")
        self.runner: Runner | None = None
        # Flow instance representing the current workflow
        self.flow = Flow(version="1.0", meta=Meta(name=self.current_flow_path.stem))

        root = QWidget(); self.setCentralWidget(root)
        root_v = QVBoxLayout(root); root_v.setContentsMargins(0,0,0,0); root_v.setSpacing(0)
        self.header = HeaderBar()
        root_v.addWidget(self.header)

        # 中央3分割
        hsplit = QSplitter(Qt.Orientation.Horizontal)
        self.action_palette = ActionPalette()
        center_scroll = QScrollArea(); center_scroll.setWidgetResizable(True)
        self.canvas = DottedCanvas()
        self.add_btn = add_step_button()
        # When clicked, QPushButton emits a boolean 'checked' state. Use a lambda
        # to discard this parameter so add_step receives no unintended arguments.
        self.add_btn.clicked.connect(lambda: self.add_step())
        self.canvas.v.addWidget(self.add_btn)
        self.step_count = 0
        self.canvas.list.orderChanged.connect(self._sync_flow_order)

        # undo/redo and clipboard support
        self.undo_stack: list[list[Step]] = []
        self.redo_stack: list[list[Step]] = []
        QShortcut(QKeySequence.StandardKey.Copy, self, self.copy_step)
        QShortcut(QKeySequence.StandardKey.Paste, self, self.paste_step)
        QShortcut(QKeySequence.StandardKey.Undo, self, self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self.redo)

        # 初期カード配置
        self.add_step(icon="🖱️", action=TEXT["action_click"], record=False)
        self.add_step(icon="🧾", action=TEXT["action_input"], record=False)
        self.add_step(icon="📊", action=TEXT["action_write_excel"], record=False)
        self.add_step(icon="🌐", action=TEXT["action_web_navigate"], record=False)
        center_scroll.setWidget(self.canvas)
        self.prop_panel = PropertiesPanel()
        hsplit.addWidget(self.action_palette)
        hsplit.addWidget(center_scroll)
        hsplit.addWidget(self.prop_panel)
        hsplit.setSizes([280, 720, 360])
        self.canvas.list.stepSelected.connect(self.prop_panel.load_step)
        if self.canvas.list.count():
            self.canvas.list.setCurrentRow(0)

        # ⬇︎ ログは縦Splitterで高さを安定化
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(hsplit)

        self.log_panel = LogPanel()
        vsplit.addWidget(self.log_panel)
        self._step_log_bridge = _StepLogBridge(self.log_panel)
        set_step_log_callback(self._step_log_bridge.step_logged.emit)
        vsplit.setCollapsible(0, False)
        vsplit.setCollapsible(1, False)
        vsplit.setSizes([640, 180])  # 上:中央エリア / 下:ログ（固定気味）

        root_v.addWidget(vsplit)

        # Hot-reload support: watch flow files and action definitions for changes
        self._flow_handler = FlowChangeHandler()
        self._flow_handler.file_changed.connect(self.on_flow_updated)
        self._observer = Observer()
        self._observer.schedule(self._flow_handler, ".", recursive=False)
        self._observer.schedule(self._flow_handler, "workflow", recursive=True)
        self._observer.schedule(self._flow_handler, "flows", recursive=True)
        self._observer.start()

        # expose the global queue for convenience
        self.recorded_actions_q = recorded_actions_q

        # Queue for recorded actions coming from external recorder
        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._process_record_queue)
        self._record_timer.start(100)

        # シグナル接続
        self.header.run_btn.clicked.connect(self.on_run)
        self.header.stop_btn.clicked.connect(self.on_stop)
        self.header.dry_btn.clicked.connect(self.on_dry)
        self.header.sett_btn.clicked.connect(self.on_setting)
        self.header.hist_btn.clicked.connect(self.show_history)
        self.header.appr_btn.clicked.connect(self.request_approval)
        self.header.adv_chk.toggled.connect(self._on_adv_toggled)
        # Add steps with a single click from the action palette instead of requiring a double-click
        self.action_palette.list.itemClicked.connect(self.palette_clicked)

        # Launch onboarding wizard on first run and load existing configuration
        self._config_path = Path.home() / ".config" / "rpa_project" / "config.json"
        self._config: dict[str, object] = {}
        if self._config_path.exists():
            try:
                self._config = json.loads(self._config_path.read_text())
            except Exception:
                self._config = {}

        # Load individual settings with fallbacks
        self.role = self._config.get("role", "user")
        self.theme = self._config.get("theme", "light")
        self.default_timeout = self._config.get("default_timeout", 1000)

        show_wizard = False
        if not os.environ.get("PYTEST_CURRENT_TEST") and not self._config.get(
            "onboarding_complete"
        ):
            show_wizard = True
        if show_wizard:
            wizard = OnboardingWizard(self)
            if wizard.exec():
                self._config["onboarding_complete"] = True
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                self._config_path.write_text(json.dumps(self._config, indent=2))

        initial_adv = self.role == "admin"
        self.header.adv_chk.setChecked(initial_adv)
        self._on_adv_toggled(initial_adv)

    def save_flow(self) -> None:
        """Persist the current flow to ``self.current_flow_path``."""
        data = asdict(self.flow)
        self.current_flow_path.write_text(json.dumps(data, indent=2))

    def record_callback(self, action: dict) -> None:
        """Callback for :func:`workflow.gui_tools.record_web`.

        The recorder pushes normalised actions here which are then queued for
        insertion on the GUI thread.
        """

        recorded_actions_q.put(action)

    def _process_record_queue(self) -> None:
        while not recorded_actions_q.empty():
            action = recorded_actions_q.get()
            title = action.get("action") or action.get("type") or "Recorded"
            self.add_step(action=title)

    def record_history(self) -> None:
        """Store current step order for undo support."""
        self.undo_stack.append(copy.deepcopy(self.flow.steps))
        self.redo_stack.clear()

    def _refresh_titles(self) -> None:
        for i in range(self.canvas.list.count()):
            item = self.canvas.list.item(i)
            card = self.canvas.list.itemWidget(item)
            title_lbl = card.findChild(QLabel, "title")
            if title_lbl:
                title_lbl.setText(f"Step {i+1}")

    def _emit_step_selected(self, item: QListWidgetItem) -> Step:
        self.canvas.list.setCurrentItem(item)
        step = item.data(Qt.ItemDataRole.UserRole)
        self.canvas.list.stepSelected.emit(step)
        return step

    def _add_step_card(self, step: Step, index: int | None = None, icon: str = "🧩") -> None:
        card = StepCard(icon, "", step.action)
        item = QListWidgetItem()
        item.setSizeHint(card.size())
        item.setData(Qt.ItemDataRole.UserRole, step)
        if index is None:
            self.canvas.list.addItem(item)
        else:
            self.canvas.list.insertItem(index, item)
        self.canvas.list.setItemWidget(item, card)
        card.clicked.connect(lambda _, it=item: self._emit_step_selected(it))
        card.more.clicked.connect(lambda _, it=item, btn=card.more: self._show_step_menu(it, btn))

    def _show_step_menu(self, item: QListWidgetItem, button: QPushButton) -> None:
        self._emit_step_selected(item)
        menu = QMenu(self)
        menu.addAction("コピー", self.copy_step)
        menu.addAction("削除", self.delete_step)
        menu.addAction("詳細編集", self.edit_step)
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _rebuild_from_flow(self) -> None:
        self.canvas.list.clear()
        for step in self.flow.steps:
            self._add_step_card(step)
        self._refresh_titles()

    def _sync_flow_order(self) -> None:
        self.record_history()
        new_steps: list[Step] = []
        for i in range(self.canvas.list.count()):
            item = self.canvas.list.item(i)
            step = item.data(Qt.ItemDataRole.UserRole)
            new_steps.append(step)
        self.flow.steps = new_steps
        self._refresh_titles()
        self.save_flow()

    def add_step(self, icon="🧩", action=TEXT["action_new_step"], index: int | None = None, record: bool = True):
        """Insert a new step card."""
        if record:
            self.record_history()
        self.step_count += 1
        step = Step(id=f"s{self.step_count}", action=action)
        if index is None:
            self.flow.steps.append(step)
        else:
            self.flow.steps.insert(index, step)
        self._add_step_card(step, index=index, icon=icon)
        self._refresh_titles()
        self.save_flow()

    def copy_step(self) -> None:
        row = self.canvas.list.currentRow()
        if row < 0:
            return
        item = self.canvas.list.item(row)
        step = item.data(Qt.ItemDataRole.UserRole)
        self._copied_step = copy.deepcopy(step)

    def paste_step(self) -> None:
        if not hasattr(self, "_copied_step"):
            return
        row = self.canvas.list.currentRow()
        self.add_step(action=self._copied_step.action, index=row + 1 if row >= 0 else None)

    def delete_step(self) -> None:
        row = self.canvas.list.currentRow()
        if row < 0:
            return
        self.record_history()
        self.canvas.list.takeItem(row)
        del self.flow.steps[row]
        self._refresh_titles()
        self.save_flow()

    def edit_step(self) -> None:
        row = self.canvas.list.currentRow()
        if row < 0:
            return
        item = self.canvas.list.item(row)
        step = self._emit_step_selected(item)
        self.prop_panel.load_step(step)
        self.prop_panel.update()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.flow.steps))
        self.flow.steps = self.undo_stack.pop()
        self._rebuild_from_flow()
        self.save_flow()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.flow.steps))
        self.flow.steps = self.redo_stack.pop()
        self._rebuild_from_flow()
        self.save_flow()

    def palette_clicked(self, item):
        """Handle single-clicks on the action palette."""
        # Ignore section headers which are rendered in bold
        if item.font().bold():
            return
        self.add_step(action=item.text().strip())

    def _on_adv_toggled(self, checked: bool) -> None:
        self.prop_panel.set_advanced_visible(checked)
        self.action_palette.set_advanced_visible(checked)

    def on_run(self):
        """Execute the current flow and log the result."""
        self.log_panel.add_row(
            datetime.now().strftime("%H:%M:%S"), "Run", "Started", True
        )
        try:
            data = json.loads(self.current_flow_path.read_text())
            flow = Flow.from_dict(data)
            self.runner = Runner()
            try:
                self.runner.run_flow(flow)
            finally:
                # Clear the reference so subsequent stops don't target a stale runner
                self.runner = None
        except Exception as exc:  # pragma: no cover - defensive
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"),
                "Run",
                f"Failed: {exc}",
                False,
            )
        else:
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"), "Run", "Finished", True
            )

    def on_stop(self):
        """Request the running flow to stop and log the outcome."""
        now = datetime.now().strftime("%H:%M:%S")
        if not self.runner:
            self.log_panel.add_row(now, "Run", "No active flow", False)
            return
        try:
            self.runner.stop()
        except Exception as exc:  # pragma: no cover - defensive
            self.log_panel.add_row(now, "Run", f"Stop failed: {exc}", False)
        else:
            self.log_panel.add_row(now, "Run", "Stop requested", True)
        finally:
            # Always drop the runner reference once a stop was requested
            self.runner = None

    def on_dry(self):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_panel.add_row(now, "Dry Run", "Started", True)
        try:
            data = json.loads(self.current_flow_path.read_text())
            flow = Flow.from_dict(data)
            self.runner = Runner()
            try:
                result = self.runner.run_flow(flow, auto_resume=True)
            finally:
                # Ensure the runner doesn't persist beyond this dry run
                self.runner = None
        except Exception as exc:  # pragma: no cover - defensive
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"),
                "Dry Run",
                f"Failed: {exc}",
                False,
            )
        else:
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"),
                "Dry Run",
                f"Finished: {json.dumps(result)}",
                True,
            )

    def on_setting(self):
        self.log_panel.add_row(
            datetime.now().strftime("%H:%M:%S"), "Setting", "Opened", True
        )
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            # Refresh cached values after save
            self.theme = self._config.get("theme", "light")
            self.default_timeout = self._config.get("default_timeout", 1000)
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"), "Setting", "Saved", True
            )
        else:
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"), "Setting", "Canceled", False
            )

    def show_history(self):
        flow = Flow.from_dict(json.loads(self.current_flow_path.read_text()))
        Runner().view_flow(flow)
        dlg = FlowHistoryDialog(self.current_flow_path)
        dlg.exec()

    def request_approval(self):
        now = datetime.now().strftime("%H:%M:%S")
        try:
            data = json.loads(self.current_flow_path.read_text())
            flow = Flow.from_dict(data)
            Runner().request_approval(flow)
        except Exception as exc:  # pragma: no cover - defensive
            self.log_panel.add_row(
                now,
                TEXT["approval_request"],
                TEXT["approval_failed"].format(exc=exc),
                False,
            )
            QMessageBox.critical(
                self,
                TEXT["approval_request"],
                TEXT["approval_failed"].format(exc=exc),
            )
        else:
            self.log_panel.add_row(
                now,
                TEXT["approval_request"],
                TEXT["approval_sent"],
                True,
            )
            QMessageBox.information(
                self,
                TEXT["approval_request"],
                TEXT["approval_sent"],
            )

    def on_flow_updated(self, path: str):
        """Refresh UI when the watched flow definition changes."""
        self.log_panel.add_row(
            datetime.now().strftime("%H:%M:%S"), "Watcher", f"{path} changed", True
        )
        p = Path(path)
        if p.is_relative_to(Path("flows")):
            data = json.loads(p.read_text())
            flow = Flow.from_dict(data)
            runner = Runner()
            runner.edit_flow(flow)
            runner.publish_flow(flow)
            tag = f"{p.stem}/{datetime.now().strftime('%Y%m%d%H%M%S')}"
            commit = commit_and_tag(p, f"update {p.name}", tag)
            self.log_panel.add_row(
                datetime.now().strftime("%H:%M:%S"), "Git", f"{commit[:7]} tagged {tag}", True
            )

    def closeEvent(self, event):  # type: ignore[override]
        if hasattr(self, "_observer"):
            self._observer.stop()
            self._observer.join()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("*{ font-family:'Segoe UI','Noto Sans JP','Yu Gothic UI',sans-serif; font-size:12px; }")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
