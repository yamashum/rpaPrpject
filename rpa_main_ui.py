# rpa_mock_ui_fixed.py
import sys
from datetime import datetime
from PyQt6.QtCore import Qt, QFileSystemWatcher
from PyQt6.QtGui import QFont, QPainter, QColor, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFrame, QScrollArea,
    QFormLayout, QLineEdit, QSpinBox, QCheckBox, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)

# ---------- 中央キャンバス（ドット背景＋カード） ----------
class DottedCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color:#FAFBFE;")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(40, 24, 40, 24)
        self.v.setSpacing(18)
        self.v.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(QColor("#E9EDF6"), 1))
        step = 16
        for y in range(0, self.height(), step):
            for x in range(0, self.width(), step):
                p.drawPoint(x, y)
        p.end()

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
        more.setStyleSheet("QPushButton{background:#fff;border:1px solid #E5EAF5;border-radius:14px;color:#6B7A99;font-size:16px;} QPushButton:hover{background:#F6F8FD;}")
        h.addWidget(ic); h.addLayout(texts); h.addStretch(1); h.addWidget(more)

def arrow_label():
    a = QLabel("↓")
    a.setAlignment(Qt.AlignmentFlag.AlignCenter)
    a.setStyleSheet("color:#8AA0C6; font-size:20px;")
    return a

def add_step_button():
    btn = QPushButton("+  Add Step")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(160, 36)
    btn.setStyleSheet("""
        QPushButton{background:#fff;color:#3C4B69;border:1px dashed #C9D3E6;border-radius:8px;font-weight:600;}
        QPushButton:hover{background:#F6F8FD;}
    """)
    return btn

# ---------- 左パレット ----------
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
        self.list = QListWidget()
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
        form.addRow("Seekitor Editor", QPushButton("Open…"))
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
        self.run_btn = QPushButton("▶  Run"); self.run_btn.setObjectName("primary")
        self.stop_btn = QPushButton("□  Stop"); self.stop_btn.setProperty("class","ghost")
        self.dry_btn  = QPushButton("◻  Dry Run"); self.dry_btn.setProperty("class","ghost")
        self.sett_btn = QPushButton("⚙  Setting"); self.sett_btn.setProperty("class","ghost")
        left = QHBoxLayout(); left.setSpacing(8)
        left.addWidget(self.run_btn); left.addWidget(self.stop_btn); left.addWidget(self.dry_btn); left.addWidget(self.sett_btn)
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
        self.table.setItem(r, 2, st)
        self.table.setRowHeight(r, 26)

# ---------- メイン ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RPA Designer Mock")
        self.resize(1280, 860)

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
        # 初期カード配置
        self.add_step(icon="🖱️", action="Click")
        self.add_step(icon="🧾", action="Input")
        self.add_step(icon="📊", action="Write to Excel")
        self.add_step(icon="🌐", action="Web - navigate")
        center_scroll.setWidget(self.canvas)
        right = PropertiesPanel()
        hsplit.addWidget(self.action_palette); hsplit.addWidget(center_scroll); hsplit.addWidget(right)
        hsplit.setSizes([280, 720, 360])

        # ⬇︎ ログは縦Splitterで高さを安定化
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(hsplit)

        self.log_panel = LogPanel()
        vsplit.addWidget(self.log_panel)
        vsplit.setCollapsible(0, False)
        vsplit.setCollapsible(1, False)
        vsplit.setSizes([640, 180])  # 上:中央エリア / 下:ログ（固定気味）

        root_v.addWidget(vsplit)

        # Hot-reload support: watch the sample flow for changes and log updates
        self._watcher = QFileSystemWatcher(["sample_flow.json"])
        self._watcher.fileChanged.connect(self.on_flow_updated)

        # シグナル接続
        self.header.run_btn.clicked.connect(self.on_run)
        self.header.stop_btn.clicked.connect(self.on_stop)
        self.header.dry_btn.clicked.connect(self.on_dry)
        self.header.sett_btn.clicked.connect(self.on_setting)
        self.action_palette.list.itemDoubleClicked.connect(self.palette_double_clicked)

    def add_step(self, icon="🧩", action="New Step"):
        """Insert a new step card above the add button."""
        self.step_count += 1
        card = StepCard(icon, f"Step {self.step_count}", action)
        idx = self.canvas.v.indexOf(self.add_btn)
        self.canvas.v.insertWidget(idx, card)
        idx = self.canvas.v.indexOf(self.add_btn)
        self.canvas.v.insertWidget(idx, arrow_label())

    def palette_double_clicked(self, item):
        if item.font().bold():
            return
        self.add_step(action=item.text().strip())

    def on_run(self):
        self.log_panel.add_row(datetime.now().strftime("%H:%M:%S"), "Run", "Started", True)

    def on_stop(self):
        self.log_panel.add_row(datetime.now().strftime("%H:%M:%S"), "Run", "Stopped", False)

    def on_dry(self):
        self.log_panel.add_row(datetime.now().strftime("%H:%M:%S"), "Dry Run", "Started", True)

    def on_setting(self):
        self.log_panel.add_row(datetime.now().strftime("%H:%M:%S"), "Setting", "Opened", True)

    def on_flow_updated(self, path: str):
        """Refresh UI when the watched flow definition changes."""
        self.log_panel.add_row(
            datetime.now().strftime("%H:%M:%S"), "Watcher", f"{path} changed", True
        )

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("*{ font-family:'Segoe UI','Noto Sans JP','Yu Gothic UI',sans-serif; font-size:12px; }")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
