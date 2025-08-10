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
)
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from workflow.flow_git import commit_and_tag, history as flow_history, diff as flow_diff, mark_approved
from workflow.flow import Flow, Step, Meta
from workflow.runner import Runner
from workflow.logging import set_step_log_callback

# Global queue receiving actions recorded by external modules
recorded_actions_q: "queue.Queue[dict]" = queue.Queue()


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
    """Simple introductory wizard shown on first launch."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Getting Started")

        # Page 1 - flow creation
        page1 = QWizardPage()
        page1.setTitle("Create a Flow")
        l1 = QVBoxLayout()
        label1 = QLabel(
            "Use the action palette to build a flow by adding the required steps."
        )
        label1.setWordWrap(True)
        l1.addWidget(label1)
        page1.setLayout(l1)

        # Page 2 - execution
        page2 = QWizardPage()
        page2.setTitle("Run the Flow")
        l2 = QVBoxLayout()
        label2 = QLabel(
            "Press the Run button to execute your flow or Dry Run to test without side effects."
        )
        label2.setWordWrap(True)
        l2.addWidget(label2)
        page2.setLayout(l2)

        self.addPage(page1)
        self.addPage(page2)

# ---------- 中央キャンバス（ドット背景＋カード） ----------
class StepListWidget(QListWidget):
    """List widget that supports internal drag & drop to reorder steps."""

    orderChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        # Allow both internal moves and external drops
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSpacing(18)
        self.setStyleSheet("QListWidget{background:transparent;border:none;}")

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
        more = QPushButton("⋯")
        more.setFixedSize(28, 28)
        more.setStyleSheet(
            "QPushButton{background:#fff;border:1px solid #E5EAF5;border-radius:14px;color:#6B7A99;font-size:16px;} QPushButton:hover{background:#F6F8FD;}"
        )
        h.addWidget(ic); h.addLayout(texts); h.addStretch(1); h.addWidget(more)

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
        title = QLabel("Action Palette"); title.setObjectName("title")
        self.list = _PaletteListWidget()
        v.addWidget(title); v.addWidget(self.list)
        self._section("Window Operations", ["Launch / Attach", "Activate / Bring to Front"])
        self._section("Mouse and Keyboard", ["Click", "Double Click", "Type Text"])
        self._section("Element Interaction (UIA)", ["Set Value", "Select", "Check / Uncheck"])
        self._section("Image and OCR", ["Find Image", "OCR Read"])
        self._section("Coordinate Click", ["Click (X,Y)"])
        self._section("Office / Excel / Word", ["Open", "Write Cell", "Save"])
        self._section("Conditions and Loops", ["If", "For Each"])
        self._section("Exception Handling", ["Try / Catch"])

    def _section(self, header, items):
        h = QListWidgetItem(f"  {header}"); f = QFont(); f.setBold(True); h.setFont(f)
        self.list.addItem(h)
        for it in items:
            self.list.addItem(QListWidgetItem(f"    {it}"))

# ---------- 右プロパティ ----------
class PropertiesPanel(QWidget):
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
        v = QVBoxLayout(self); v.setContentsMargins(20,20,20,20); v.setSpacing(12)
        head = QLabel("Properties"); head.setObjectName("header")
        v.addWidget(head)
        form = QFormLayout(); form.setHorizontalSpacing(12); form.setVerticalSpacing(10)
        act = QComboBox(); act.addItems(["Click", "Input", "Write to Excel", "Web - Navigate"])
        selector = QLineEdit("any01   UIA/image...")
        out = QLineEdit("result1")
        to = QSpinBox(); to.setRange(0, 120000); to.setValue(3000); to.setSuffix(" ms")
        re = QSpinBox(); re.setRange(0, 20); re.setValue(3)
        chk = QCheckBox("Save screenshot"); chk.setChecked(True)
        form.addRow("Action", act)
        form.addRow("Seekitor Editor", QPushButton("開く…"))
        form.addRow(selector)
        form.addRow("Output Variable", out)
        form.addRow("Timeout", to)
        form.addRow("Retry Count", re)
        v.addLayout(form); v.addWidget(QLabel("On Failure")); v.addWidget(chk); v.addStretch(1)

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

        # basic context help so first-time users understand the actions
        self.run_btn.setToolTip("Execute the current workflow")
        self.stop_btn.setToolTip("Stop the running workflow")
        self.dry_btn.setToolTip("Run the workflow without side effects")
        self.sett_btn.setToolTip("Open settings")
        self.hist_btn.setToolTip("Show execution history")
        self.appr_btn.setToolTip("Request approval for this flow")
        left = QHBoxLayout(); left.setSpacing(8)
        left.addWidget(self.run_btn); left.addWidget(self.stop_btn); left.addWidget(self.dry_btn); left.addWidget(self.sett_btn)
        left.addWidget(self.hist_btn); left.addWidget(self.appr_btn)
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
        self.table.setHorizontalHeaderLabels(["Time", "Step", "Status"])
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
        self.setWindowTitle("Flow History")
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Commit", "Message"])
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
        self.setWindowTitle("RPA Designer Mock")
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
        self.add_btn.clicked.connect(self.add_step)
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
        self.add_step(icon="🖱️", action="Click", record=False)
        self.add_step(icon="🧾", action="Input", record=False)
        self.add_step(icon="📊", action="Write to Excel", record=False)
        self.add_step(icon="🌐", action="Web - navigate", record=False)
        center_scroll.setWidget(self.canvas)
        right = PropertiesPanel()
        hsplit.addWidget(self.action_palette); hsplit.addWidget(center_scroll); hsplit.addWidget(right)
        hsplit.setSizes([280, 720, 360])

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
        # Add steps with a single click from the action palette instead of requiring a double-click
        self.action_palette.list.itemClicked.connect(self.palette_clicked)

        # Launch onboarding wizard on first run
        self._config_path = Path.home() / ".config" / "rpa_project" / "config.json"
        show_wizard = False
        cfg = {}
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            if self._config_path.exists():
                try:
                    cfg = json.loads(self._config_path.read_text())
                except Exception:
                    cfg = {}
            if not cfg.get("onboarding_complete"):
                show_wizard = True
                self._config = cfg
        if show_wizard:
            wizard = OnboardingWizard(self)
            if wizard.exec():
                cfg["onboarding_complete"] = True
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                self._config_path.write_text(json.dumps(cfg, indent=2))

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

    def add_step(self, icon="🧩", action="New Step", index: int | None = None, record: bool = True):
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
        self.log_panel.add_row(datetime.now().strftime("%H:%M:%S"), "Setting", "Opened", True)

    def show_history(self):
        flow = Flow.from_dict(json.loads(self.current_flow_path.read_text()))
        Runner().view_flow(flow)
        dlg = FlowHistoryDialog(self.current_flow_path)
        dlg.exec()

    def request_approval(self):
        self.show_history()

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
