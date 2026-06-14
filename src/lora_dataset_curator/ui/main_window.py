from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QDir, QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from lora_dataset_curator.actions import append_action_log, build_action_plan, execute_plan
from lora_dataset_curator.cache import (
    load_decisions,
    load_duplicate_result,
    save_decisions,
    save_duplicate_result,
)
from lora_dataset_curator.duplicate_analysis import (
    DEFAULT_MAX_PERCEPTUAL_PAIRS,
    DuplicateAnalysisResult,
    analyze_duplicates,
    prepare_hash_cache,
)
from lora_dataset_curator.models import ActionName, DuplicateGroup, ImageRecord
from lora_dataset_curator.scanner import scan_dataset
from lora_dataset_curator.storage import ensure_app_data_dirs, load_default_profile

ProgressCallback = Callable[[int, int, str], None]
DECISION_LABELS = {"move": "이동", "delete": "삭제 예정", "skip": "보류"}
DECISION_KEYS = {
    Qt.Key.Key_A: "move",
    Qt.Key.Key_D: "delete",
    Qt.Key.Key_S: "skip",
}


class GroupBoundaryDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        if index.data(Qt.ItemDataRole.UserRole + 1):
            painter.save()
            painter.setPen(QPen(QColor("#4a4a4a"), 3))
            painter.drawLine(option.rect.topLeft(), option.rect.topRight())
            painter.restore()


class ImagePreview(QWidget):
    def __init__(
        self,
        *,
        minimum_width: int = 320,
        minimum_height: int = 220,
        maximum_height: int = 320,
    ) -> None:
        super().__init__()
        self.pixmap = QPixmap()
        self.message = "선택된 이미지 없음"
        self.setMinimumSize(minimum_width, minimum_height)
        if maximum_height > 0:
            self.setMaximumHeight(maximum_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_image(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.pixmap = QPixmap()
            self.message = "미리보기를 표시할 수 없습니다."
        else:
            self.pixmap = pixmap
            self.message = ""
        self.update()

    def clear(self) -> None:
        self.pixmap = QPixmap()
        self.message = "선택된 이미지 없음"
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().mid().color())
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        content_rect = self.rect().adjusted(8, 8, -8, -8)
        if self.pixmap.isNull():
            painter.setPen(self.palette().text().color())
            painter.drawText(content_rect, Qt.AlignmentFlag.AlignCenter, self.message)
            return

        scaled = self.pixmap.scaled(
            content_rect.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = content_rect.x() + (content_rect.width() - scaled.width()) // 2
        y = content_rect.y() + (content_rect.height() - scaled.height()) // 2
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(x, y, scaled)


class GroupImageTile(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.preview = ImagePreview(
            minimum_width=220,
            minimum_height=180,
            maximum_height=0,
        )
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)

    def set_record(self, record: ImageRecord, *, recommended: bool, decision: str = "") -> None:
        self.preview.set_image(record.image_path)
        prefix = "[keep] " if recommended else ""
        self.title_label.setText(f"{prefix}{record.image_path.name}")
        size = f"{record.width}x{record.height}" if record.width and record.height else "?"
        sidecars = []
        sidecars.append("txt" if record.caption_path else "no txt")
        sidecars.append("json" if record.metadata_path else "no json")
        decision_label = DECISION_LABELS.get(decision, "미결정")
        self.meta_label.setText(f"{size} | {decision_label} | {', '.join(sidecars)}")


class FloatingPreviewWindow(QWidget):
    def __init__(self, owner: MainWindow) -> None:
        super().__init__(
            owner,
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.owner = owner
        self.setWindowTitle("이미지 검수")
        self.resize(900, 900)
        self.preview = ImagePreview(
            minimum_width=640,
            minimum_height=640,
            maximum_height=16777215,
        )
        self.status_label = QLabel("←/→ 이동 | A 이동 | D 삭제 예정 | S 보류")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview, stretch=1)
        layout.addWidget(self.status_label)
        self.create_shortcuts()

    def create_shortcuts(self) -> None:
        self.decision_shortcuts: dict[str, QShortcut] = {}
        for key, action in (("A", "move"), ("D", "delete"), ("S", "skip")):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda name=action: self.apply_decision_shortcut(name))
            self.decision_shortcuts[action] = shortcut

        self.next_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.next_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.next_shortcut.activated.connect(lambda: self.owner.select_relative_record(1))
        self.previous_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.previous_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.previous_shortcut.activated.connect(lambda: self.owner.select_relative_record(-1))

    def apply_decision_shortcut(self, action: str) -> None:
        self.owner.set_current_decision(action)
        self.owner.select_relative_record(1)

    def show_record(self, record: ImageRecord | None) -> None:
        if record is None:
            self.preview.clear()
            self.status_label.setText("선택된 이미지 없음")
            return
        self.preview.set_image(record.image_path)
        decision = self.owner.review_decisions.get(str(record.image_path), "")
        label = DECISION_LABELS.get(decision, "미결정")
        self.status_label.setText(
            f"{record.image_path.name} | {label} | ←/→ 이동 | A 이동 | D 삭제 예정 | S 보류"
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.owner.select_relative_record(1)
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.owner.select_relative_record(-1)
            return
        action = DECISION_KEYS.get(key)
        if action is not None:
            self.owner.set_current_decision(action)
            self.owner.select_relative_record(1)
            return
        super().keyPressEvent(event)


class TaskWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[ProgressCallback], object]) -> None:
        super().__init__()
        self.task = task

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.task(self.progress.emit))
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(
        self,
        input_dir: Path | None = None,
        output_dir: Path | None = None,
        *,
        background_tasks: bool = True,
    ) -> None:
        super().__init__()
        self.records: list[ImageRecord] = []
        self.scan_order: dict[Path, int] = {}
        self.record_group_ids: dict[Path, str] = {}
        self.review_decisions: dict[str, str] = {}
        self.current_record: ImageRecord | None = None
        self.duplicate_result: DuplicateAnalysisResult | None = None
        self.background_tasks = background_tasks
        self.active_thread: QThread | None = None
        self.active_worker: TaskWorker | None = None
        self.floating_preview: FloatingPreviewWindow | None = None
        self.app_paths = ensure_app_data_dirs()
        self.profile = load_default_profile()

        self.setWindowTitle("LoRA Dataset Curator")
        self.resize(1280, 800)

        self.input_path = QLineEdit(str(input_dir) if input_dir else "")
        self.output_path = QLineEdit(str(output_dir) if output_dir else str(Path.cwd() / "output"))
        self.summary_label = QLabel("아직 스캔하지 않았습니다.")
        self.status_label = QLabel("대기 중")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.preview_label = ImagePreview()

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["그룹", "결정", "파일", "크기", "캡션", "메타데이터", "Post ID", "등급"]
        )
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setItemDelegate(GroupBoundaryDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

        self.caption_text = QPlainTextEdit()
        self.caption_text.setReadOnly(True)
        self.caption_meta_label = QLabel("")
        self.caption_meta_label.setWordWrap(True)
        self.metadata_text = QPlainTextEdit()
        self.metadata_text.setReadOnly(True)
        self.info_text = QPlainTextEdit()
        self.info_text.setReadOnly(True)
        self.plan_text = QPlainTextEdit()
        self.plan_text.setReadOnly(True)
        self.duplicate_summary_label = QLabel("아직 중복 분석을 실행하지 않았습니다.")
        self.use_perceptual_checkbox = QCheckBox("pHash/dHash 사용")
        duplicate_settings = self.profile.get("duplicates", {})
        if not isinstance(duplicate_settings, dict):
            duplicate_settings = {}
        self.use_perceptual_checkbox.setChecked(bool(duplicate_settings.get("use_perceptual")))
        self.phash_threshold = QSpinBox()
        self.phash_threshold.setRange(0, 64)
        self.phash_threshold.setValue(int(duplicate_settings.get("phash_threshold", 6)))
        self.dhash_threshold = QSpinBox()
        self.dhash_threshold.setRange(0, 64)
        self.dhash_threshold.setValue(int(duplicate_settings.get("dhash_threshold", 6)))

        self.group_table = QTableWidget(0, 4)
        self.group_table.setHorizontalHeaderLabels(
            ["그룹", "개수", "이유", "추천 keep"]
        )
        self.group_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_table.itemSelectionChanged.connect(self.on_group_selection_changed)

        self.group_member_table = QTableWidget(0, 6)
        self.group_member_table.setHorizontalHeaderLabels(
            ["추천", "결정", "파일", "크기", "캡션", "메타데이터"]
        )
        self.group_member_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )
        self.group_member_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_member_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_member_table.itemSelectionChanged.connect(self.on_group_member_selection_changed)
        self.group_preview_container = QWidget()
        self.group_preview_layout = QGridLayout(self.group_preview_container)
        self.group_preview_area = QScrollArea()
        self.group_preview_area.setWidgetResizable(True)
        self.group_preview_area.setWidget(self.group_preview_container)

        self.setCentralWidget(self.build_layout())
        self.create_menu()
        self.create_shortcuts()

        if input_dir is not None:
            self.scan()

    def build_layout(self) -> QWidget:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addLayout(self.build_top_bar())
        container_layout.addLayout(self.build_progress_row())
        container_layout.addWidget(self.build_tabs(self.build_review_tab()))
        return container

    def build_top_bar(self) -> QHBoxLayout:
        input_button = QPushButton("찾기")
        input_button.clicked.connect(self.choose_input_dir)
        output_button = QPushButton("찾기")
        output_button.clicked.connect(self.choose_output_dir)
        self.scan_button = QPushButton("스캔")
        self.scan_button.clicked.connect(self.scan)
        self.execute_button = QPushButton("실행")
        self.execute_button.clicked.connect(self.execute_review_decisions)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_path)
        input_row.addWidget(input_button)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path)
        output_row.addWidget(output_button)

        form = QFormLayout()
        form.addRow("입력 폴더", input_row)
        form.addRow("출력 폴더", output_row)

        top_bar = QHBoxLayout()
        top_bar.addLayout(form, stretch=1)
        top_bar.addWidget(self.scan_button)
        top_bar.addWidget(self.execute_button)
        return top_bar

    def build_progress_row(self) -> QHBoxLayout:
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.status_label, stretch=1)
        progress_row.addWidget(self.progress_bar, stretch=2)
        return progress_row

    def build_review_tab(self) -> QWidget:
        left = QWidget()
        left.setMinimumWidth(520)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.summary_label)
        left_layout.addWidget(self.table)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(self.preview_label, stretch=1)
        preview_layout.addLayout(self.build_action_buttons())

        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.addWidget(QLabel("파일 정보"))
        info_layout.addWidget(self.info_text)

        caption_panel = QWidget()
        caption_layout = QVBoxLayout(caption_panel)
        caption_layout.addWidget(QLabel("캡션"))
        caption_layout.addWidget(self.caption_text)
        caption_layout.addWidget(self.caption_meta_label)

        metadata_panel = QWidget()
        metadata_layout = QVBoxLayout(metadata_panel)
        metadata_layout.addWidget(QLabel("메타데이터"))
        metadata_layout.addWidget(self.metadata_text)

        plan_panel = QWidget()
        plan_layout = QVBoxLayout(plan_panel)
        plan_layout.addWidget(QLabel("Dry-run 이동 계획"))
        plan_layout.addWidget(self.plan_text)

        self.review_detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.review_detail_splitter.setChildrenCollapsible(False)
        for panel in (preview_panel, info_panel, caption_panel, metadata_panel, plan_panel):
            self.review_detail_splitter.addWidget(panel)
        self.review_detail_splitter.setSizes([300, 150, 150, 150, 120])

        self.review_splitter = QSplitter()
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.addWidget(left)
        self.review_splitter.addWidget(self.review_detail_splitter)
        self.review_splitter.setStretchFactor(0, 3)
        self.review_splitter.setStretchFactor(1, 2)
        self.review_splitter.setSizes([760, 520])
        return self.review_splitter

    def build_tabs(self, review_widget: QWidget) -> QTabWidget:
        self.tabs = QTabWidget()
        self.tabs.addTab(review_widget, "검수")
        self.tabs.addTab(self.build_duplicate_tab(), "중복 그룹")
        return self.tabs

    def build_duplicate_tab(self) -> QWidget:
        self.analyze_button = QPushButton("분석")
        self.analyze_button.clicked.connect(self.analyze_duplicate_groups)
        self.prepare_cache_button = QPushButton("캐시 준비")
        self.prepare_cache_button.clicked.connect(self.prepare_duplicate_cache)

        controls_widget = QWidget()
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.prepare_cache_button)
        controls.addWidget(self.use_perceptual_checkbox)
        controls.addWidget(QLabel("pHash 기준"))
        controls.addWidget(self.phash_threshold)
        controls.addWidget(QLabel("dHash 기준"))
        controls.addWidget(self.dhash_threshold)
        controls.addWidget(self.duplicate_summary_label)
        controls.addStretch()
        controls_widget.setLayout(controls)

        self.duplicate_splitter = QSplitter()
        self.duplicate_splitter.setChildrenCollapsible(False)
        member_panel = QWidget()
        member_layout = QVBoxLayout(member_panel)
        member_layout.addWidget(self.group_member_table, stretch=1)

        self.duplicate_splitter.addWidget(self.group_table)
        self.duplicate_splitter.addWidget(member_panel)
        self.duplicate_splitter.setStretchFactor(0, 2)
        self.duplicate_splitter.setStretchFactor(1, 3)
        self.duplicate_splitter.setSizes([520, 760])

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("그룹 이미지 미리보기"))
        preview_layout.addWidget(self.group_preview_area, stretch=1)

        self.duplicate_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.duplicate_vertical_splitter.setChildrenCollapsible(False)
        self.duplicate_vertical_splitter.addWidget(self.duplicate_splitter)
        self.duplicate_vertical_splitter.addWidget(preview_panel)
        self.duplicate_vertical_splitter.setStretchFactor(0, 3)
        self.duplicate_vertical_splitter.setStretchFactor(1, 2)
        self.duplicate_vertical_splitter.setSizes([420, 260])

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(controls_widget)
        layout.addWidget(self.duplicate_vertical_splitter, stretch=1)
        return tab

    def build_action_buttons(self) -> QVBoxLayout:
        button_layout = QVBoxLayout()
        command_row = QHBoxLayout()
        decision_row = QHBoxLayout()
        preview_button = QPushButton("큰 미리보기")
        preview_button.setMinimumWidth(100)
        preview_button.clicked.connect(self.show_floating_preview)
        command_row.addWidget(preview_button)
        for label, action in (
            ("보관", "keep"),
            ("이동", "move"),
            ("격리", "quarantine"),
            ("건너뛰기", "skip"),
        ):
            button = QPushButton(label)
            button.setMinimumWidth(72)
            button.clicked.connect(lambda _checked=False, name=action: self.show_plan(name))
            command_row.addWidget(button)

        open_button = QPushButton("폴더 열기")
        open_button.setMinimumWidth(92)
        open_button.clicked.connect(self.open_file_location)
        source_button = QPushButton("출처 열기")
        source_button.setMinimumWidth(92)
        source_button.clicked.connect(self.open_source_url)
        command_row.addWidget(open_button)
        command_row.addWidget(source_button)
        command_row.addStretch()
        for label, action in (
            ("A 이동 결정", "move"),
            ("D 삭제 예정", "delete"),
            ("S 보류", "skip"),
        ):
            button = QPushButton(label)
            button.setMinimumWidth(104)
            button.clicked.connect(
                lambda _checked=False, name=action: self.set_current_decision(name)
            )
            decision_row.addWidget(button)
        decision_row.addStretch()
        button_layout.addLayout(command_row)
        button_layout.addLayout(decision_row)
        return button_layout

    def create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("파일")
        scan_action = QAction("스캔", self)
        scan_action.triggered.connect(self.scan)
        file_menu.addAction(scan_action)

        exit_action = QAction("종료", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def create_shortcuts(self) -> None:
        self.decision_shortcuts: dict[str, QShortcut] = {}
        for key, action in (("A", "move"), ("D", "delete"), ("S", "skip")):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda name=action: self.apply_decision_shortcut(name))
            self.decision_shortcuts[action] = shortcut

        self.next_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.next_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.next_shortcut.activated.connect(lambda: self.select_relative_record(1))
        self.previous_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.previous_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.previous_shortcut.activated.connect(lambda: self.select_relative_record(-1))

    def apply_decision_shortcut(self, action: str) -> None:
        self.set_current_decision(action)
        self.select_relative_record(1)

    def choose_input_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "데이터셋 폴더 선택",
            self.input_path.text(),
        )
        if path:
            self.input_path.setText(QDir.toNativeSeparators(path))

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "출력 폴더 선택",
            self.output_path.text(),
        )
        if path:
            self.output_path.setText(QDir.toNativeSeparators(path))

    def scan(self) -> None:
        input_dir = Path(self.input_path.text()).expanduser()
        if not input_dir.exists():
            QMessageBox.warning(
                self,
                "스캔 실패",
                f"입력 폴더가 없습니다:\n{input_dir}",
            )
            return

        if self.background_tasks:
            self.start_background_task(
                lambda progress_callback: scan_dataset(
                    input_dir,
                    progress_callback=progress_callback,
                ),
                self.finish_scan,
                "스캔을 시작했습니다.",
            )
            return

        self.records = scan_dataset(input_dir)
        self.finish_scan(self.records)

    def finish_scan(self, records: list[ImageRecord]) -> None:
        self.records = records
        self.scan_order = {record.image_path: index for index, record in enumerate(records)}
        self.record_group_ids = {}
        self.review_decisions = load_decisions(self.output_root())

        self.populate_table()
        self.clear_duplicate_groups()
        if self.records:
            self.table.selectRow(0)
        else:
            self.clear_details()

    def populate_table(self) -> None:
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            size = f"{record.width}x{record.height}" if record.width and record.height else ""
            values = [
                self.record_group_ids.get(record.image_path, ""),
                DECISION_LABELS.get(self.review_decisions.get(str(record.image_path), ""), ""),
                record.image_path.name,
                size,
                "yes" if record.caption_path else "no",
                "yes" if record.metadata_path else "no",
                record.post_id or "",
                record.rating or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.apply_table_item_style(item, record, row)
                self.table.setItem(row, column, item)

        caption_count = sum(record.caption_path is not None for record in self.records)
        metadata_count = sum(record.metadata_path is not None for record in self.records)
        self.summary_label.setText(
            f"이미지: {len(self.records)} | "
            f"캡션: {caption_count}개 연결, {len(self.records) - caption_count}개 누락 | "
            f"메타데이터: {metadata_count}개 연결, {len(self.records) - metadata_count}개 누락"
        )

    def on_selection_changed(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        row = selected[0].row()
        if row < 0 or row >= len(self.records):
            return
        self.set_current_record(self.records[row])

    def set_current_record(self, record: ImageRecord) -> None:
        self.current_record = record
        self.plan_text.clear()
        self.caption_text.setPlainText(record.caption_text)
        self.caption_meta_label.setText(self.format_caption_meta(record))
        self.metadata_text.setPlainText(
            json.dumps(record.raw_metadata, ensure_ascii=False, indent=2)
            if record.raw_metadata
            else "{}"
        )
        self.info_text.setPlainText(self.format_info(record))
        self.load_preview(record.image_path)
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.show_record(record)

    def clear_details(self) -> None:
        self.current_record = None
        self.preview_label.clear()
        self.caption_text.clear()
        self.caption_meta_label.clear()
        self.metadata_text.clear()
        self.info_text.clear()
        self.plan_text.clear()

    def load_preview(self, path: Path) -> None:
        self.preview_label.set_image(path)

    def show_floating_preview(self) -> None:
        if self.floating_preview is None:
            self.floating_preview = FloatingPreviewWindow(self)
        self.floating_preview.show_record(self.current_record)
        self.floating_preview.show()
        self.floating_preview.raise_()
        self.floating_preview.activateWindow()

    def select_relative_record(self, offset: int) -> None:
        if not self.records:
            return
        try:
            current_index = self.records.index(self.current_record) if self.current_record else 0
        except ValueError:
            current_index = 0
        next_index = min(max(current_index + offset, 0), len(self.records) - 1)
        self.table.selectRow(next_index)
        self.table.scrollToItem(self.table.item(next_index, 0))

    def set_current_decision(self, action: str) -> None:
        if self.current_record is None:
            return
        self.review_decisions[str(self.current_record.image_path)] = action
        save_decisions(self.output_root(), self.review_decisions)
        self.current_record.review_status = action
        self.populate_table()
        self.select_record(self.current_record)
        self.refresh_current_group_members()
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.show_record(self.current_record)

    def select_record(self, record: ImageRecord) -> None:
        try:
            row = self.records.index(record)
        except ValueError:
            return
        self.table.selectRow(row)

    def refresh_current_group_members(self) -> None:
        if self.duplicate_result is None:
            return
        selected = self.group_table.selectionModel().selectedRows()
        if not selected:
            return
        row = selected[0].row()
        if 0 <= row < len(self.duplicate_result.groups):
            self.populate_group_members(self.duplicate_result.groups[row])

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.select_relative_record(1)
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.select_relative_record(-1)
            return
        action = DECISION_KEYS.get(key)
        if action is not None:
            self.set_current_decision(action)
            self.select_relative_record(1)
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.current_record is not None:
            self.load_preview(self.current_record.image_path)

    def show_plan(self, action: ActionName) -> None:
        if self.current_record is None:
            return
        output_dir = Path(self.output_path.text()).expanduser()
        plan = build_action_plan(self.current_record, output_dir, action, dry_run=True)
        lines = [f"작업: {plan.action}", "Dry run: true"]
        lines.extend(f"{move.source} -> {move.target}" for move in plan.moves)
        self.plan_text.setPlainText("\n".join(lines))

    def open_file_location(self) -> None:
        if self.current_record is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_record.image_path.parent)))

    def open_source_url(self) -> None:
        if self.current_record is None or not self.current_record.source_url:
            QMessageBox.information(self, "출처 URL", "사용 가능한 출처 URL이 없습니다.")
            return
        QDesktopServices.openUrl(QUrl(self.current_record.source_url))

    def execute_review_decisions(self) -> None:
        actionable = [
            record
            for record in self.records
            if self.review_decisions.get(str(record.image_path)) in {"move", "delete"}
        ]
        if not actionable:
            QMessageBox.information(
                self,
                "실행",
                "이동 또는 삭제 예정으로 결정한 이미지가 없습니다.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "결정 실행",
            f"{len(actionable)}개 이미지와 연결된 sidecar 파일을 출력 폴더로 이동합니다.\n"
            "삭제 예정은 실제 삭제가 아니라 rejected 폴더로 이동합니다.\n"
            "계속할까요?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        log_path = self.output_root() / "action_log.csv"
        moved_count = 0
        for record in actionable:
            action = self.review_decisions.get(str(record.image_path))
            if action not in {"move", "delete"}:
                continue
            plan = build_action_plan(record, self.output_root(), action, dry_run=False)
            execute_plan(plan)
            append_action_log(log_path, record, plan)
            moved_count += 1

        save_decisions(self.output_root(), self.review_decisions)
        QMessageBox.information(self, "실행 완료", f"{moved_count}개 이미지 결정을 실행했습니다.")
        self.scan()

    def prepare_duplicate_cache(self) -> None:
        if not self.records:
            QMessageBox.information(self, "캐시 준비", "먼저 데이터셋을 스캔하세요.")
            return

        input_dir = Path(self.input_path.text()).expanduser()
        include_perceptual = self.use_perceptual_checkbox.isChecked()
        if self.background_tasks:
            self.start_background_task(
                lambda progress_callback: prepare_hash_cache(
                    self.records,
                    hash_cache_root=input_dir,
                    include_perceptual=include_perceptual,
                    progress_callback=progress_callback,
                ),
                self.finish_prepare_cache,
                "해시 캐시 준비를 시작했습니다.",
            )
            return

        prepare_hash_cache(
            self.records,
            hash_cache_root=input_dir,
            include_perceptual=include_perceptual,
        )
        self.finish_prepare_cache(None)

    def finish_prepare_cache(self, _result: object) -> None:
        self.duplicate_summary_label.setText(
            f"캐시 준비 완료: {len(self.records)}개 이미지"
        )

    def analyze_duplicate_groups(self) -> None:
        if not self.records:
            QMessageBox.information(self, "중복 분석", "먼저 데이터셋을 스캔하세요.")
            return

        use_perceptual = self.use_perceptual_checkbox.isChecked()
        if use_perceptual and max(self.phash_threshold.value(), self.dhash_threshold.value()) > 15:
            QMessageBox.warning(
                self,
                "pHash/dHash 분석 제한",
                "현재 bucket 후보 검색은 pHash/dHash 기준값 15까지만 지원합니다.\n"
                "기준값을 낮춘 뒤 다시 실행하세요.",
            )
            return

        input_dir = Path(self.input_path.text()).expanduser()
        cached_result = load_duplicate_result(
            self.output_root(),
            input_dir,
            self.records,
            use_perceptual=use_perceptual,
            phash_threshold=self.phash_threshold.value(),
            dhash_threshold=self.dhash_threshold.value(),
            result_type=DuplicateAnalysisResult,
        )
        if cached_result is not None:
            self.finish_duplicate_analysis(cached_result)
            self.set_busy(False, "캐시된 중복 그룹을 불러왔습니다.")
            return

        if self.background_tasks:
            phash_threshold = self.phash_threshold.value()
            dhash_threshold = self.dhash_threshold.value()
            hash_cache_root = input_dir
            self.start_background_task(
                lambda progress_callback: analyze_duplicates(
                    self.records,
                    use_perceptual=use_perceptual,
                    phash_threshold=phash_threshold,
                    dhash_threshold=dhash_threshold,
                    max_perceptual_pairs=DEFAULT_MAX_PERCEPTUAL_PAIRS,
                    hash_cache_root=hash_cache_root,
                    progress_callback=progress_callback,
                ),
                self.finish_duplicate_analysis,
                "중복 분석을 시작했습니다.",
            )
            return

        self.finish_duplicate_analysis(
            analyze_duplicates(
                self.records,
                use_perceptual=self.use_perceptual_checkbox.isChecked(),
                phash_threshold=self.phash_threshold.value(),
                dhash_threshold=self.dhash_threshold.value(),
                max_perceptual_pairs=DEFAULT_MAX_PERCEPTUAL_PAIRS,
                hash_cache_root=input_dir,
            )
        )

    def finish_duplicate_analysis(self, result: DuplicateAnalysisResult) -> None:
        self.duplicate_result = result
        self.sort_records_by_duplicate_groups()
        self.populate_table()
        self.populate_group_table()
        if self.records:
            save_duplicate_result(
                self.output_root(),
                Path(self.input_path.text()).expanduser(),
                self.records,
                result,
                use_perceptual=self.use_perceptual_checkbox.isChecked(),
                phash_threshold=self.phash_threshold.value(),
                dhash_threshold=self.dhash_threshold.value(),
            )

    def clear_duplicate_groups(self) -> None:
        self.duplicate_result = None
        self.record_group_ids = {}
        self.group_table.setRowCount(0)
        self.group_member_table.setRowCount(0)
        self.clear_group_previews()
        self.duplicate_summary_label.setText("아직 중복 분석을 실행하지 않았습니다.")

    def sort_records_by_duplicate_groups(self) -> None:
        if self.duplicate_result is None:
            return

        self.record_group_ids = {}
        group_rank: dict[str, int] = {}
        member_rank: dict[Path, int] = {}
        for group_index, group in enumerate(self.duplicate_result.groups):
            group_rank[group.group_id] = group_index
            for member_index, record in enumerate(self.sorted_group_records(group)):
                self.record_group_ids[record.image_path] = group.group_id
                member_rank[record.image_path] = member_index

        self.records.sort(
            key=lambda record: (
                0 if record.image_path in self.record_group_ids else 1,
                group_rank.get(self.record_group_ids.get(record.image_path, ""), 0),
                member_rank.get(record.image_path, self.scan_order.get(record.image_path, 0)),
                self.scan_order.get(record.image_path, 0),
            )
        )

    def populate_group_table(self) -> None:
        if self.duplicate_result is None:
            return
        groups = self.duplicate_result.groups
        self.group_table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            reasons = ", ".join(self.duplicate_result.group_reasons.get(group.group_id, []))
            keep = group.recommended_keep.image_path.name if group.recommended_keep else ""
            values = [group.group_id, str(len(group.images)), reasons, keep]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.group_table.setItem(row, column, item)

        self.duplicate_summary_label.setText(
            f"그룹: {len(groups)} | 후보 pair: {len(self.duplicate_result.pairs)}"
        )
        if groups:
            self.group_table.selectRow(0)
        else:
            self.group_member_table.setRowCount(0)

    def on_group_selection_changed(self) -> None:
        if self.duplicate_result is None:
            return
        selected = self.group_table.selectionModel().selectedRows()
        if not selected:
            return
        row = selected[0].row()
        if row < 0 or row >= len(self.duplicate_result.groups):
            return
        self.populate_group_members(self.duplicate_result.groups[row])

    def populate_group_members(self, group: DuplicateGroup) -> None:
        records = self.sorted_group_records(group)
        self.group_member_table.setRowCount(len(records))
        for row, record in enumerate(records):
            size = f"{record.width}x{record.height}" if record.width and record.height else ""
            values = [
                "yes" if record == group.recommended_keep else "",
                DECISION_LABELS.get(self.review_decisions.get(str(record.image_path), ""), ""),
                record.image_path.name,
                size,
                "yes" if record.caption_path else "no",
                "yes" if record.metadata_path else "no",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self.apply_member_item_style(item, record)
                self.group_member_table.setItem(row, column, item)
        if records:
            self.group_member_table.selectRow(0)
        self.populate_group_previews(group, records)

    @staticmethod
    def sorted_group_records(group: DuplicateGroup) -> list[ImageRecord]:
        return sorted(
            group.images,
            key=lambda record: (
                record != group.recommended_keep,
                -record.resolution_pixels,
                -(record.file_size or 0),
                record.image_path.name,
            ),
        )

    def populate_group_previews(
        self,
        group: DuplicateGroup,
        records: list[ImageRecord],
    ) -> None:
        self.clear_group_previews()
        for index, record in enumerate(records):
            tile = GroupImageTile()
            tile.set_record(
                record,
                recommended=record == group.recommended_keep,
                decision=self.review_decisions.get(str(record.image_path), ""),
            )
            self.group_preview_layout.addWidget(tile, index // 3, index % 3)

    def clear_group_previews(self) -> None:
        while self.group_preview_layout.count():
            item = self.group_preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def on_group_member_selection_changed(self) -> None:
        selected = self.group_member_table.selectionModel().selectedRows()
        if not selected:
            return
        item = self.group_member_table.item(selected[0].row(), 0)
        if item is None:
            return
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, ImageRecord):
            self.set_current_record(record)

    def start_background_task(
        self,
        task: Callable[[ProgressCallback], object],
        on_finished: Callable[[object], None],
        message: str,
    ) -> None:
        if self.active_thread is not None:
            QMessageBox.information(self, "작업 진행 중", "현재 작업이 끝난 뒤 다시 시도하세요.")
            return

        self.set_busy(True, message)
        thread = QThread(self)
        worker = TaskWorker(task)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self.update_progress)
        worker.finished.connect(lambda result: self.finish_background_task(result, on_finished))
        worker.failed.connect(self.fail_background_task)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self.active_thread = thread
        self.active_worker = worker
        thread.start()

    def finish_background_task(
        self,
        result: object,
        on_finished: Callable[[object], None],
    ) -> None:
        try:
            on_finished(result)
        except Exception:
            self.fail_background_task(traceback.format_exc())
            return
        self.set_busy(False, "완료")
        self.active_thread = None
        self.active_worker = None

    def fail_background_task(self, message: str) -> None:
        self.set_busy(False, "실패")
        self.active_thread = None
        self.active_worker = None
        QMessageBox.critical(self, "작업 실패", message)

    def update_progress(self, current: int, total: int, message: str) -> None:
        if self.active_thread is None:
            return
        if total <= 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(f"{message} ({current}/{total})" if total else message)

    def set_busy(self, busy: bool, message: str) -> None:
        self.scan_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy)
        self.prepare_cache_button.setEnabled(not busy)
        self.execute_button.setEnabled(not busy)
        self.status_label.setText(message)
        if busy:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)

    def apply_table_item_style(
        self,
        item: QTableWidgetItem,
        record: ImageRecord,
        row: int,
    ) -> None:
        group_id = self.record_group_ids.get(record.image_path)
        previous_group = (
            self.record_group_ids.get(self.records[row - 1].image_path)
            if row > 0
            else None
        )
        item.setData(Qt.ItemDataRole.UserRole + 1, bool(group_id and group_id != previous_group))
        if group_id:
            item.setBackground(QColor("#f1f5f9"))
        decision = self.review_decisions.get(str(record.image_path))
        if decision == "move":
            item.setBackground(QColor("#dcfce7"))
        elif decision == "delete":
            item.setBackground(QColor("#fee2e2"))
        elif decision == "skip":
            item.setBackground(QColor("#fef9c3"))

    def apply_member_item_style(self, item: QTableWidgetItem, record: ImageRecord) -> None:
        decision = self.review_decisions.get(str(record.image_path))
        if decision == "move":
            item.setBackground(QColor("#dcfce7"))
        elif decision == "delete":
            item.setBackground(QColor("#fee2e2"))
        elif decision == "skip":
            item.setBackground(QColor("#fef9c3"))

    def output_root(self) -> Path:
        return Path(self.output_path.text()).expanduser().resolve()

    def format_caption_meta(self, record: ImageRecord) -> str:
        size = f"{record.width}x{record.height}" if record.width and record.height else "unknown"
        file_size = format_file_size(record.file_size or 0)
        group_id = self.record_group_ids.get(record.image_path, "그룹 없음")
        decision = DECISION_LABELS.get(
            self.review_decisions.get(str(record.image_path), ""),
            "미결정",
        )
        sidecars = [
            "txt 있음" if record.caption_path else "txt 없음",
            "json 있음" if record.metadata_path else "json 없음",
        ]
        return (
            f"크기: {size} | 용량: {file_size} | {group_id} | "
            f"결정: {decision} | {', '.join(sidecars)}"
        )

    @staticmethod
    def format_info(record: ImageRecord) -> str:
        lines = [
            f"경로: {record.image_path}",
            f"캡션: {record.caption_path or '없음'}",
            f"메타데이터: {record.metadata_path or '없음'}",
            f"해상도: {record.width or '?'}x{record.height or '?'}",
            f"파일 크기: {record.file_size or 0} bytes",
            f"Post ID: {record.post_id or ''}",
            f"MD5: {record.source_md5 or ''}",
            f"출처: {record.source_url or ''}",
            f"등급: {record.rating or ''}",
            f"작가 태그: {', '.join(record.tags_artist)}",
            f"캐릭터 태그: {', '.join(record.tags_character)}",
            f"저작권 태그: {', '.join(record.tags_copyright)}",
            f"일반 태그: {', '.join(record.tags_general[:80])}",
        ]
        return "\n".join(lines)


def format_file_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def run_gui(input_dir: Path | None = None, output_dir: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(input_dir=input_dir, output_dir=output_dir)
    window.show()
    return app.exec()
