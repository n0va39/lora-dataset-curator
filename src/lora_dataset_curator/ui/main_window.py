from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QDir, QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from lora_dataset_curator.actions import build_action_plan
from lora_dataset_curator.duplicate_analysis import (
    DEFAULT_MAX_PERCEPTUAL_PAIRS,
    DuplicateAnalysisResult,
    analyze_duplicates,
    pair_count,
)
from lora_dataset_curator.models import ActionName, DuplicateGroup, ImageRecord
from lora_dataset_curator.scanner import scan_dataset

ProgressCallback = Callable[[int, int, str], None]


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
        except Exception as exc:
            self.failed.emit(str(exc))


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
        self.current_record: ImageRecord | None = None
        self.duplicate_result: DuplicateAnalysisResult | None = None
        self.background_tasks = background_tasks
        self.active_thread: QThread | None = None
        self.active_worker: TaskWorker | None = None

        self.setWindowTitle("LoRA Dataset Curator")
        self.resize(1280, 800)

        self.input_path = QLineEdit(str(input_dir) if input_dir else "")
        self.output_path = QLineEdit(str(output_dir) if output_dir else str(Path.cwd() / "output"))
        self.summary_label = QLabel("아직 스캔하지 않았습니다.")
        self.status_label = QLabel("대기 중")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.preview_label = QLabel("선택된 이미지 없음")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(360, 300)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        self.preview_label.setStyleSheet("border: 1px solid #bbb; background: #fafafa;")

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["파일", "크기", "캡션", "메타데이터", "Post ID", "등급"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

        self.caption_text = QPlainTextEdit()
        self.caption_text.setReadOnly(True)
        self.metadata_text = QPlainTextEdit()
        self.metadata_text.setReadOnly(True)
        self.info_text = QPlainTextEdit()
        self.info_text.setReadOnly(True)
        self.plan_text = QPlainTextEdit()
        self.plan_text.setReadOnly(True)
        self.duplicate_summary_label = QLabel("아직 중복 분석을 실행하지 않았습니다.")
        self.use_perceptual_checkbox = QCheckBox("pHash/dHash 사용")
        self.phash_threshold = QSpinBox()
        self.phash_threshold.setRange(0, 64)
        self.phash_threshold.setValue(6)
        self.dhash_threshold = QSpinBox()
        self.dhash_threshold.setRange(0, 64)
        self.dhash_threshold.setValue(6)

        self.group_table = QTableWidget(0, 4)
        self.group_table.setHorizontalHeaderLabels(
            ["그룹", "개수", "이유", "추천 keep"]
        )
        self.group_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_table.itemSelectionChanged.connect(self.on_group_selection_changed)

        self.group_member_table = QTableWidget(0, 5)
        self.group_member_table.setHorizontalHeaderLabels(
            ["추천", "파일", "크기", "캡션", "메타데이터"]
        )
        self.group_member_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.group_member_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_member_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_member_table.itemSelectionChanged.connect(self.on_group_member_selection_changed)

        self.setCentralWidget(self.build_layout())
        self.create_menu()

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

        details = QWidget()
        details.setMinimumWidth(420)
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(self.preview_label)
        details_layout.addLayout(self.build_action_buttons())
        details_layout.addWidget(QLabel("파일 정보"))
        details_layout.addWidget(self.info_text)
        details_layout.addWidget(QLabel("캡션"))
        details_layout.addWidget(self.caption_text)
        details_layout.addWidget(QLabel("메타데이터"))
        details_layout.addWidget(self.metadata_text)
        details_layout.addWidget(QLabel("Dry-run 이동 계획"))
        details_layout.addWidget(self.plan_text)

        self.review_splitter = QSplitter()
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.addWidget(left)
        self.review_splitter.addWidget(details)
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

        controls = QHBoxLayout()
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.use_perceptual_checkbox)
        controls.addWidget(QLabel("pHash 기준"))
        controls.addWidget(self.phash_threshold)
        controls.addWidget(QLabel("dHash 기준"))
        controls.addWidget(self.dhash_threshold)
        controls.addStretch()

        self.duplicate_splitter = QSplitter()
        self.duplicate_splitter.setChildrenCollapsible(False)
        self.duplicate_splitter.addWidget(self.group_table)
        self.duplicate_splitter.addWidget(self.group_member_table)
        self.duplicate_splitter.setStretchFactor(0, 2)
        self.duplicate_splitter.setStretchFactor(1, 3)
        self.duplicate_splitter.setSizes([520, 760])

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addLayout(controls)
        layout.addWidget(self.duplicate_summary_label)
        layout.addWidget(self.duplicate_splitter)
        return tab

    def build_action_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for label, action in (
            ("보관", "keep"),
            ("이동", "move"),
            ("격리", "quarantine"),
            ("건너뛰기", "skip"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, name=action: self.show_plan(name))
            row.addWidget(button)

        open_button = QPushButton("폴더 열기")
        open_button.clicked.connect(self.open_file_location)
        source_button = QPushButton("출처 열기")
        source_button.clicked.connect(self.open_source_url)
        row.addWidget(open_button)
        row.addWidget(source_button)
        return row

    def create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("파일")
        scan_action = QAction("스캔", self)
        scan_action.triggered.connect(self.scan)
        file_menu.addAction(scan_action)

        exit_action = QAction("종료", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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
        self.metadata_text.setPlainText(
            json.dumps(record.raw_metadata, ensure_ascii=False, indent=2)
            if record.raw_metadata
            else "{}"
        )
        self.info_text.setPlainText(self.format_info(record))
        self.load_preview(record.image_path)

    def clear_details(self) -> None:
        self.current_record = None
        self.preview_label.setText("선택된 이미지 없음")
        self.preview_label.setPixmap(QPixmap())
        self.caption_text.clear()
        self.metadata_text.clear()
        self.info_text.clear()
        self.plan_text.clear()

    def load_preview(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText("미리보기를 표시할 수 없습니다.")
            self.preview_label.setPixmap(QPixmap())
            return
        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

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

    def analyze_duplicate_groups(self) -> None:
        if not self.records:
            QMessageBox.information(self, "중복 분석", "먼저 데이터셋을 스캔하세요.")
            return

        use_perceptual = self.use_perceptual_checkbox.isChecked()
        total_pairs = pair_count(len(self.records))
        if use_perceptual and total_pairs > DEFAULT_MAX_PERCEPTUAL_PAIRS:
            QMessageBox.warning(
                self,
                "pHash/dHash 분석 제한",
                "pHash/dHash는 모든 이미지 쌍을 비교합니다.\n"
                f"현재 데이터셋은 {total_pairs:,}개 쌍이 필요해서 "
                f"기본 제한 {DEFAULT_MAX_PERCEPTUAL_PAIRS:,}개를 초과합니다.\n"
                "우선 pHash/dHash를 끄고 metadata/SHA256 기준으로 분석하세요.",
            )
            return

        if self.background_tasks:
            phash_threshold = self.phash_threshold.value()
            dhash_threshold = self.dhash_threshold.value()
            self.start_background_task(
                lambda progress_callback: analyze_duplicates(
                    self.records,
                    use_perceptual=use_perceptual,
                    phash_threshold=phash_threshold,
                    dhash_threshold=dhash_threshold,
                    max_perceptual_pairs=DEFAULT_MAX_PERCEPTUAL_PAIRS,
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
            )
        )

    def finish_duplicate_analysis(self, result: DuplicateAnalysisResult) -> None:
        self.duplicate_result = result
        self.populate_group_table()

    def clear_duplicate_groups(self) -> None:
        self.duplicate_result = None
        self.group_table.setRowCount(0)
        self.group_member_table.setRowCount(0)
        self.duplicate_summary_label.setText("아직 중복 분석을 실행하지 않았습니다.")

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
        records = sorted(
            group.images,
            key=lambda record: (
                record != group.recommended_keep,
                -record.resolution_pixels,
                -(record.file_size or 0),
                record.image_path.name,
            ),
        )
        self.group_member_table.setRowCount(len(records))
        for row, record in enumerate(records):
            size = f"{record.width}x{record.height}" if record.width and record.height else ""
            values = [
                "yes" if record == group.recommended_keep else "",
                record.image_path.name,
                size,
                "yes" if record.caption_path else "no",
                "yes" if record.metadata_path else "no",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self.group_member_table.setItem(row, column, item)
        if records:
            self.group_member_table.selectRow(0)

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
        on_finished(result)
        self.set_busy(False, "완료")
        self.active_thread = None
        self.active_worker = None

    def fail_background_task(self, message: str) -> None:
        self.set_busy(False, "실패")
        self.active_thread = None
        self.active_worker = None
        QMessageBox.critical(self, "작업 실패", message)

    def update_progress(self, current: int, total: int, message: str) -> None:
        if total <= 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(f"{message} ({current}/{total})" if total else message)

    def set_busy(self, busy: bool, message: str) -> None:
        self.scan_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy)
        self.status_label.setText(message)
        if busy:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)

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


def run_gui(input_dir: Path | None = None, output_dir: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(input_dir=input_dir, output_dir=output_dir)
    window.show()
    return app.exec()
