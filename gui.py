"""营业执照英译 — 登记窗口式桌面面板。"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PySide6.QtCore import (
    QObject,
    QSettings,
    QSize,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QPalette,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

COL_FILE, COL_STATUS, COL_OUTPUT, COL_NOTE = range(4)
STATUS_WAIT, STATUS_RUN, STATUS_DONE, STATUS_SKIP, STATUS_ERR = (
    "等待",
    "转换中",
    "完成",
    "非A格式",
    "失败",
)

INK = "#1B2430"
STYLE = """
QMainWindow, QWidget#Root {
    background: #C5CEDA;
    color: #1B2430;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QWidget { color: #1B2430; }
QFrame#Card {
    background: #E4EAF1;
    border: 1px solid #9AA7B6;
    border-radius: 2px;
}
QLabel { color: #1B2430; }
QLabel#Brand {
    color: #1B2430;
    font-family: "Times New Roman", "Nimbus Roman", serif;
    font-size: 28px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QLabel#Tag {
    color: #C8102E;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
}
QLabel#Sub { color: #4A5868; font-size: 12px; }
QLabel#Section {
    color: #1B2430;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    padding-left: 8px;
    border-left: 3px solid #C8102E;
}
QLineEdit {
    color: #1B2430;
    background: #F4F7FB;
    border: 1px solid #8A96A3;
    padding: 7px 10px;
    selection-background-color: #C8102E;
    selection-color: #FFFFFF;
}
QLineEdit:focus { border: 1px solid #C8102E; background: #FBFCFD; }
QLineEdit:disabled { color: #5B6B7C; background: #D3DBE5; border-color: #AEB7C2; }
QCheckBox { color: #1B2430; spacing: 8px; }
QPushButton {
    background: #D9E1EB;
    border: 1px solid #8A96A3;
    padding: 6px 12px;
    color: #1B2430;
}
QPushButton:hover { background: #CDD6E2; }
QPushButton:disabled { color: #7A8794; background: #D5DCE6; }
QPushButton#Primary {
    background: #C8102E;
    color: #FFFFFF;
    border: 1px solid #9E0C24;
    font-weight: 700;
    padding: 8px 22px;
    min-width: 108px;
}
QPushButton#Primary:hover { background: #B10E29; }
QPushButton#Primary:disabled { background: #C49AA2; border-color: #C49AA2; color: #F7F9FB; }
QToolButton {
    color: #1B2430;
    background: #D9E1EB;
    border: 1px solid #8A96A3;
    padding: 4px 10px;
}
QToolButton:hover { background: #CDD6E2; }
QTableWidget {
    color: #1B2430;
    background: #EEF2F6;
    border: 1px solid #8A96A3;
    gridline-color: #C5CDD8;
    selection-background-color: #E8C5CB;
    selection-color: #1B2430;
    alternate-background-color: #E2E8F0;
}
QTableWidget::item {
    color: #1B2430;
    padding: 6px 8px;
    background: #EEF2F6;
}
QTableWidget::item:alternate { background: #E2E8F0; color: #1B2430; }
QTableWidget::item:selected { background: #E8C5CB; color: #1B2430; }
QHeaderView::section {
    background: #C9D3DF;
    border: none;
    border-right: 1px solid #AEB7C2;
    border-bottom: 1px solid #8A96A3;
    padding: 8px;
    font-weight: 700;
    color: #1B2430;
}
QPlainTextEdit#Log {
    background: #1B2430;
    color: #D5DCE6;
    border: 1px solid #121821;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}
QStatusBar {
    background: #AEB8C6;
    color: #1B2430;
    border-top: 1px solid #8A96A3;
    font-weight: 600;
}
QScrollBar:vertical { background: #D5DCE6; width: 10px; }
QScrollBar::handle:vertical { background: #8A96A3; min-height: 24px; }
QLabel#DropHint { color: #4A5868; font-size: 13px; }
QLabel#PreviewHint {
    color: #4A5868;
    background: #D5DCE6;
    border: 1px dashed #8A96A3;
}
QLabel#PreviewPage {
    color: #1B2430;
    background: #D5DCE6;
    border: 1px solid #8A96A3;
}
QLabel#PreviewCap { color: #4A5868; font-size: 12px; }
"""


def collect_images(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        path = Path(path)
        if path.is_dir():
            children = sorted(
                child for child in path.iterdir() if child.is_file() and child.suffix.lower() in IMAGE_EXTS
            )
            files.extend(children)
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            files.append(path)
    unique: list[Path] = []
    for item in files:
        key = item.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def open_path(path: Path) -> None:
    if not path:
        return
    target = path if path.exists() else path.parent
    if not target.exists():
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def pdf_preview_pixmap(pdf_path: Path, width: int) -> QPixmap | None:
    try:
        import fitz
    except Exception:
        return None
    if not pdf_path.exists():
        return None
    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        scale = max(1.2, width / max(page.rect.width, 1) )
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = QPixmap()
        image.loadFromData(pix.tobytes("png"), "PNG")
        return image
    finally:
        doc.close()


class ConvertWorker(QObject):
    start_requested = Signal(list, str, str, str)
    log = Signal(str, str)
    item = Signal(str, str, str, str)
    preview = Signal(str)
    batch_finished = Signal(int, int, int)
    busy = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = False
        self._engine = None

    def cancel(self) -> None:
        self._cancel = True

    @Slot(list, str, str, str)
    def run_batch(self, paths: list, out_dir: str, work_dir: str, issue_date: str) -> None:
        from license_trans.classify import NotFormatA
        from license_trans.ocr import LicenseOCR
        from license_trans.pipeline import convert_image

        self._cancel = False
        self.busy.emit(True)
        date_arg = issue_date.strip() or None
        done = skipped = failed = 0
        try:
            if self._engine is None:
                self.log.emit("INFO", "加载 OCR 引擎（首次会稍慢）")
                self._engine = LicenseOCR()
                self.log.emit("INFO", "OCR 引擎就绪")
            total = len(paths)
            for index, raw in enumerate(paths, start=1):
                if self._cancel:
                    self.log.emit("WARN", "已停止，剩余文件未处理")
                    break
                src = Path(raw)
                dest = Path(out_dir) / (src.stem + ".pdf")
                self.item.emit(str(src), STATUS_RUN, "", f"{index}/{total}")
                self.log.emit("INFO", f"[{index}/{total}] {src.name}")
                try:
                    Path(out_dir).mkdir(parents=True, exist_ok=True)
                    info = convert_image(
                        src,
                        dest,
                        work_dir=work_dir or None,
                        ocr=self._engine,
                        issue_date=date_arg,
                    )
                except NotFormatA as exc:
                    skipped += 1
                    self.item.emit(str(src), STATUS_SKIP, "", str(exc))
                    self.log.emit("WARN", f"{src.name}  {exc}")
                    continue
                except Exception as exc:
                    failed += 1
                    self.item.emit(str(src), STATUS_ERR, "", str(exc))
                    self.log.emit("ERROR", f"{src.name}  {exc}")
                    continue
                warnings = list(dict.fromkeys(
                    (info["fields"].get("warnings") or []) + (info["english"].get("warnings") or [])
                ))
                note = "需核对: " + ", ".join(warnings) if warnings else "字段完整"
                self.item.emit(str(src), STATUS_DONE, str(dest), note)
                self.preview.emit(str(dest))
                self.log.emit("INFO", f"写出  {dest}")
                if warnings:
                    self.log.emit("WARN", f"{src.name}  {note}")
                done += 1
        finally:
            self.busy.emit(False)
            self.batch_finished.emit(done, skipped, failed)


class QtLogHandler(logging.Handler):
    def __init__(self, signal: Signal) -> None:
        super().__init__()
        self.signal = signal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.signal.emit(record.levelname, record.getMessage())
        except Exception:
            pass


def ink_item(text: str, *, role=None, tip: str = "", align: Qt.AlignmentFlag | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(QColor(INK))
    item.setBackground(QColor("#EEF2F6"))
    if role is not None:
        item.setData(Qt.ItemDataRole.UserRole, role)
    if tip:
        item.setToolTip(tip)
    if align is not None:
        item.setTextAlignment(align)
    return item


class IntakeTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__(0, 4)
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setHorizontalHeaderLabels(["文件", "状态", "输出 PDF", "备注"])
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_OUTPUT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_NOTE, QHeaderView.ResizeMode.Stretch)
        self.setShowGrid(True)
        self.setIconSize(QSize(18, 18))
        self.verticalHeader().setDefaultSectionSize(34)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor(INK))
        palette.setColor(QPalette.ColorRole.Base, QColor("#EEF2F6"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#E2E8F0"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(INK))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#E8C5CB"))
        self.setPalette(palette)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def row_for(self, path: str) -> int:
        for row in range(self.rowCount()):
            item = self.item(row, COL_FILE)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                return row
        return -1

    def selected_paths(self) -> list[str]:
        rows = {index.row() for index in self.selectedIndexes()}
        paths: list[str] = []
        for row in sorted(rows):
            item = self.item(row, COL_FILE)
            if item:
                paths.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return paths

    def all_paths(self) -> list[str]:
        paths: list[str] = []
        for row in range(self.rowCount()):
            item = self.item(row, COL_FILE)
            if item:
                paths.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return paths

    def add_files(self, paths: list[Path]) -> int:
        added = 0
        existing = set(self.all_paths())
        for path in paths:
            key = str(path.resolve()) if path.exists() else str(path)
            if key in existing:
                continue
            row = self.rowCount()
            self.insertRow(row)
            label = f"{path.name}  ·  {path.parent.name}"
            self.setItem(row, COL_FILE, ink_item(label, role=key, tip=key))
            self.setItem(row, COL_STATUS, self._status_item(STATUS_WAIT))
            self.setItem(row, COL_OUTPUT, ink_item("—"))
            self.setItem(row, COL_NOTE, ink_item("待转换"))
            existing.add(key)
            added += 1
        return added

    def update_row(self, path: str, status: str, output: str, note: str) -> None:
        row = self.row_for(path)
        if row < 0:
            return
        self.setItem(row, COL_STATUS, self._status_item(status))
        if output:
            self.setItem(row, COL_OUTPUT, ink_item(Path(output).name, role=output, tip=output))
        self.setItem(row, COL_NOTE, ink_item(note or "—"))

    def reset_pending(self) -> None:
        for row in range(self.rowCount()):
            status = self.item(row, COL_STATUS)
            if status and status.text() in {STATUS_ERR, STATUS_SKIP, STATUS_WAIT}:
                self.setItem(row, COL_STATUS, self._status_item(STATUS_WAIT))
                self.setItem(row, COL_NOTE, ink_item("待转换"))

    def _status_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        colors = {
            STATUS_WAIT: "#5B6B7C",
            STATUS_RUN: "#1E4E8C",
            STATUS_DONE: "#2F6F4E",
            STATUS_SKIP: "#9A6B12",
            STATUS_ERR: "#C8102E",
        }
        item.setForeground(QColor(colors.get(text, INK)))
        item.setBackground(QColor("#EEF2F6"))
        font = item.font()
        font.setBold(text != STATUS_WAIT)
        item.setFont(font)
        return item


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("执照英译")
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self.settings = QSettings("E-TRANSTAR", "LicenseTrans")
        self._busy = False
        self._last_preview = ""

        self.worker_thread = QThread(self)
        self.worker = ConvertWorker()
        self.worker.moveToThread(self.worker_thread)
        self.worker.start_requested.connect(self.worker.run_batch, Qt.ConnectionType.QueuedConnection)
        self.worker_thread.start()

        self.log_handler = QtLogHandler(self.worker.log)
        self.log_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger("license_trans").setLevel(logging.INFO)
        logging.getLogger("license_trans").propagate = False
        logging.getLogger("license_trans").addHandler(self.log_handler)

        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 8)
        layout.setSpacing(10)
        layout.addLayout(self._header())

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self._workbench())
        split.addWidget(self._log_card())
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        split.setSizes([540, 220])
        layout.addWidget(split, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._set_status("把执照照片拖进左侧，或点「加入照片」")

        self.worker.log.connect(self.append_log)
        self.worker.item.connect(self.on_item)
        self.worker.preview.connect(self.show_preview)
        self.worker.busy.connect(self.on_busy)
        self.worker.batch_finished.connect(self.on_batch_finished)

        self._restore()
        self._sync_actions()

    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        brand = QLabel("Business License")
        brand.setObjectName("Brand")
        tag = QLabel("FORMAT A  ·  公司法人执照英译")
        tag.setObjectName("Tag")
        sub = QLabel("照片进入固定英文模板，第 1 页译文，第 2 页原件")
        sub.setObjectName("Sub")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(brand)
        text.addWidget(tag)
        text.addWidget(sub)
        row.addLayout(text)
        row.addStretch(1)
        return row

    def _workbench(self) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._intake_card(), 3)
        row.addWidget(self._output_card(), 2)
        return wrap

    def _intake_card(self) -> QFrame:
        card = QFrame(objectName="Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)
        title = QLabel("收件")
        title.setObjectName("Section")
        box.addWidget(title)

        tools = QHBoxLayout()
        self.btn_add_files = QPushButton("加入照片")
        self.btn_add_dir = QPushButton("加入文件夹")
        self.btn_remove = QPushButton("移除选中")
        self.btn_clear = QPushButton("清空")
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_add_dir.clicked.connect(self.add_folder)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear_queue)
        for btn in (self.btn_add_files, self.btn_add_dir, self.btn_remove, self.btn_clear):
            tools.addWidget(btn)
        tools.addStretch(1)
        box.addLayout(tools)

        self.table = IntakeTable()
        self.table.files_dropped.connect(self.ingest)
        self.table.itemSelectionChanged.connect(self.on_select_row)
        self.table.cellDoubleClicked.connect(self.on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_menu)
        box.addWidget(self.table, 1)

        self.drop_hint = QLabel("把 jpg / png / webp / tif 拖到表格里。只处理 A 格式公司法人执照。")
        self.drop_hint.setObjectName("DropHint")
        box.addWidget(self.drop_hint)

        actions = QHBoxLayout()
        self.btn_start = QPushButton("开始转换")
        self.btn_start.setObjectName("Primary")
        self.btn_stop = QPushButton("停止")
        self.btn_start.clicked.connect(self.start_convert)
        self.btn_stop.clicked.connect(self.stop_convert)
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_stop)
        actions.addStretch(1)
        box.addLayout(actions)
        return card

    def _output_card(self) -> QFrame:
        card = QFrame(objectName="Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)
        title = QLabel("出件")
        title.setObjectName("Section")
        box.addWidget(title)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText(str(ROOT / "out"))
        btn_browse = QPushButton("浏览")
        btn_open_out = QPushButton("打开目录")
        btn_browse.clicked.connect(self.browse_out)
        btn_open_out.clicked.connect(lambda: open_path(Path(self.out_edit.text() or str(ROOT / "out"))))
        out_row.addWidget(QLabel("输出"))
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(btn_browse)
        out_row.addWidget(btn_open_out)
        box.addLayout(out_row)

        date_row = QHBoxLayout()
        self.date_check = QCheckBox("指定发证日期")
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("红章看不清时填写，例如 2022-12-09")
        self.date_edit.setEnabled(False)
        self.date_check.toggled.connect(self.date_edit.setEnabled)
        date_row.addWidget(self.date_check)
        date_row.addWidget(self.date_edit, 1)
        box.addLayout(date_row)

        cap = QLabel("英文页预览 · 第 1 页")
        cap.setObjectName("PreviewCap")
        box.addWidget(cap)
        self.preview = QLabel("转换完成后，这里预览英文页")
        self.preview.setObjectName("PreviewHint")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(280)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setScaledContents(False)
        box.addWidget(self.preview, 1)

        preview_row = QHBoxLayout()
        self.btn_open_pdf = QPushButton("打开 PDF")
        self.btn_reveal = QPushButton("打开所在目录")
        self.btn_open_pdf.clicked.connect(self.open_selected_pdf)
        self.btn_reveal.clicked.connect(self.reveal_selected_pdf)
        preview_row.addWidget(self.btn_open_pdf)
        preview_row.addWidget(self.btn_reveal)
        preview_row.addStretch(1)
        box.addLayout(preview_row)
        return card

    def _log_card(self) -> QFrame:
        card = QFrame(objectName="Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel("日志")
        title.setObjectName("Section")
        head.addWidget(title)
        head.addStretch(1)
        btn_copy = QToolButton()
        btn_copy.setText("复制")
        btn_clear = QToolButton()
        btn_clear.setText("清空")
        btn_save = QToolButton()
        btn_save.setText("保存")
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        btn_copy.clicked.connect(self.copy_log)
        btn_clear.clicked.connect(self.log_view.clear)
        btn_save.clicked.connect(self.save_log)
        head.addWidget(btn_copy)
        head.addWidget(btn_clear)
        head.addWidget(btn_save)
        box.addLayout(head)
        box.addWidget(self.log_view, 1)
        return card

    def ingest(self, paths) -> None:
        files = collect_images([Path(p) for p in paths])
        added = self.table.add_files(files)
        skipped = len(files) - added
        if added:
            self.append_log("INFO", f"加入 {added} 张照片")
        if skipped:
            self.append_log("INFO", f"跳过 {skipped} 张重复文件")
        if not files:
            self.append_log("WARN", "没有找到可用图片")
        self._sync_actions()

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择执照照片",
            self.settings.value("last_in", str(ROOT / "samples")),
            "图片 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)",
        )
        if files:
            self.settings.setValue("last_in", str(Path(files[0]).parent))
            self.ingest(files)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择照片文件夹", self.settings.value("last_in", str(ROOT))
        )
        if folder:
            self.settings.setValue("last_in", folder)
            self.ingest([folder])

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        self._sync_actions()

    def clear_queue(self) -> None:
        if self._busy:
            return
        self.table.setRowCount(0)
        self._sync_actions()

    def browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_edit.text() or str(ROOT / "out")
        )
        if folder:
            self.out_edit.setText(folder)

    def start_convert(self) -> None:
        paths = []
        for path in self.table.all_paths():
            row = self.table.row_for(path)
            status = self.table.item(row, COL_STATUS)
            if status and status.text() == STATUS_DONE:
                continue
            paths.append(path)
        if not paths:
            QMessageBox.information(self, "执照英译", "没有待转换的照片。已完成的不会重跑，可用右键「重新转换」。")
            return
        self._launch(paths)

    def reconvert_selected(self) -> None:
        paths = self.table.selected_paths()
        if not paths:
            return
        for path in paths:
            self.table.update_row(path, STATUS_WAIT, "", "待转换")
        self._launch(paths)

    def _launch(self, paths: list[str]) -> None:
        if self._busy:
            return
        out_dir = self.out_edit.text().strip() or str(ROOT / "out")
        self.out_edit.setText(out_dir)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        issue = self.date_edit.text().strip() if self.date_check.isChecked() else ""
        if self.date_check.isChecked() and not issue:
            QMessageBox.warning(self, "执照英译", "勾选了指定发证日期，请填写例如 2022-12-09。")
            return
        work_dir = str(ROOT / "work")
        self.append_log("INFO", f"开始转换 {len(paths)} 张 → {out_dir}")
        self.worker.start_requested.emit(paths, out_dir, work_dir, issue)

    def stop_convert(self) -> None:
        if self._busy:
            self.worker.cancel()
            self.append_log("WARN", "正在停止…当前这张会跑完")

    @Slot(str, str)
    def append_log(self, level: str, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        colors = {
            "INFO": "#D5DCE6",
            "WARNING": "#E2B657",
            "WARN": "#E2B657",
            "ERROR": "#F07178",
            "CRITICAL": "#F07178",
        }
        color = colors.get(level.upper(), "#D5DCE6")
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#7A8794"))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{stamp}  ")
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{level.upper():<7} {message}\n")
        self.log_view.setTextCursor(cursor)
        self.log_view.ensureCursorVisible()

    @Slot(str, str, str, str)
    def on_item(self, path: str, status: str, output: str, note: str) -> None:
        self.table.update_row(path, status, output, note)
        self._set_status(f"{Path(path).name}  ·  {status}")

    @Slot(str)
    def show_preview(self, pdf_path: str) -> None:
        self._last_preview = pdf_path
        pix = pdf_preview_pixmap(Path(pdf_path), max(360, self.preview.width() - 24))
        if pix is None or pix.isNull():
            self.preview.setObjectName("PreviewHint")
            self.preview.setText(Path(pdf_path).name)
            self.preview.style().unpolish(self.preview)
            self.preview.style().polish(self.preview)
            return
        self.preview.setObjectName("PreviewPage")
        self.preview.style().unpolish(self.preview)
        self.preview.style().polish(self.preview)
        self.preview.setPixmap(
            pix.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._sync_actions()

    @Slot(bool)
    def on_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_actions()
        if busy:
            self._set_status("转换中…")

    @Slot(int, int, int)
    def on_batch_finished(self, done: int, skipped: int, failed: int) -> None:
        self._set_status(f"完成 {done}  ·  非A {skipped}  ·  失败 {failed}")
        self.append_log("INFO", f"本批结束：完成 {done}，非A格式 {skipped}，失败 {failed}")

    def on_select_row(self) -> None:
        paths = self.table.selected_paths()
        if not paths:
            self._sync_actions()
            return
        row = self.table.row_for(paths[-1])
        out_item = self.table.item(row, COL_OUTPUT) if row >= 0 else None
        pdf = out_item.data(Qt.ItemDataRole.UserRole) if out_item else ""
        if pdf and Path(pdf).exists():
            self.show_preview(pdf)
        self._sync_actions()

    def on_double_click(self, row: int, _col: int) -> None:
        item = self.table.item(row, COL_OUTPUT)
        pdf = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if pdf:
            open_path(Path(pdf))

    def on_table_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("打开 PDF", self.open_selected_pdf)
        menu.addAction("打开所在目录", self.reveal_selected_pdf)
        menu.addAction("重新转换", self.reconvert_selected)
        menu.addSeparator()
        menu.addAction("复制文件路径", self.copy_selected_path)
        menu.addAction("移除选中", self.remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _selected_pdf(self) -> Path | None:
        paths = self.table.selected_paths()
        if paths:
            row = self.table.row_for(paths[-1])
            item = self.table.item(row, COL_OUTPUT) if row >= 0 else None
            pdf = item.data(Qt.ItemDataRole.UserRole) if item else ""
            if pdf:
                return Path(pdf)
        if self._last_preview:
            return Path(self._last_preview)
        return None

    def open_selected_pdf(self) -> None:
        path = self._selected_pdf()
        if path and path.exists():
            open_path(path)
        else:
            QMessageBox.information(self, "执照英译", "还没有可打开的 PDF。")

    def reveal_selected_pdf(self) -> None:
        path = self._selected_pdf()
        if path:
            open_path(path.parent)
        else:
            open_path(Path(self.out_edit.text() or ROOT / "out"))

    def copy_selected_path(self) -> None:
        paths = self.table.selected_paths()
        if paths:
            QApplication.clipboard().setText("\n".join(paths))

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())

    def save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存日志", str(ROOT / "work" / "gui.log"), "日志 (*.log *.txt)"
        )
        if path:
            Path(path).write_text(self.log_view.toPlainText(), encoding="utf-8")
            self.append_log("INFO", f"日志已保存  {path}")

    def _sync_actions(self) -> None:
        has_rows = self.table.rowCount() > 0
        pdf = self._selected_pdf()
        has_pdf = bool(pdf and pdf.exists())
        self.btn_start.setEnabled(has_rows and not self._busy)
        self.btn_stop.setEnabled(self._busy)
        self.btn_add_files.setEnabled(not self._busy)
        self.btn_add_dir.setEnabled(not self._busy)
        self.btn_clear.setEnabled(has_rows and not self._busy)
        self.btn_remove.setEnabled(has_rows and not self._busy)
        self.btn_open_pdf.setEnabled(has_pdf)
        self.btn_reveal.setEnabled(has_pdf or bool(self.out_edit.text().strip()))

    def _set_status(self, text: str) -> None:
        queued = self.table.rowCount()
        self.status.showMessage(f"{text}    ·    队列 {queued}")

    def _restore(self) -> None:
        saved = str(self.settings.value("out_dir") or "").strip()
        self.out_edit.setText(saved or str(ROOT / "out"))
        issue = str(self.settings.value("issue_date") or "").strip()
        if issue:
            self.date_check.setChecked(True)
            self.date_edit.setText(issue)

    def closeEvent(self, event) -> None:
        try:
            self.settings.setValue("out_dir", self.out_edit.text())
            if self.date_check.isChecked():
                self.settings.setValue("issue_date", self.date_edit.text())
            else:
                self.settings.setValue("issue_date", "")
        except Exception:
            pass
        self.worker.cancel()
        self.worker_thread.quit()
        self.worker_thread.wait(2000)
        logging.getLogger("license_trans").removeHandler(self.log_handler)
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.ingest(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._last_preview:
            self.show_preview(self._last_preview)


def apply_palette(app: QApplication) -> None:
    palette = app.palette()
    ink = QColor(INK)
    paper = QColor("#E4EAF1")
    field = QColor("#F4F7FB")
    palette.setColor(QPalette.ColorRole.Window, QColor("#C5CEDA"))
    palette.setColor(QPalette.ColorRole.WindowText, ink)
    palette.setColor(QPalette.ColorRole.Base, field)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#E2E8F0"))
    palette.setColor(QPalette.ColorRole.Text, ink)
    palette.setColor(QPalette.ColorRole.Button, QColor("#D9E1EB"))
    palette.setColor(QPalette.ColorRole.ButtonText, ink)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5B6B7C"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#C8102E"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, paper)
    palette.setColor(QPalette.ColorRole.ToolTipText, ink)
    app.setPalette(palette)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_palette(app)
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    win.append_log("INFO", "面板已打开。只转换 A 格式公司法人执照。")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
