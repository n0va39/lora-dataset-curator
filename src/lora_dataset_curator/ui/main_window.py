from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QDir, QObject, QSize, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIcon,
    QImageReader,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
    load_crop_settings,
    load_decisions,
    load_duplicate_result,
    save_crop_settings,
    save_decisions,
    save_duplicate_result,
)
from lora_dataset_curator.duplicate_analysis import (
    DEFAULT_MAX_PERCEPTUAL_PAIRS,
    DuplicateAnalysisResult,
    analyze_duplicates,
    prepare_hash_cache,
)
from lora_dataset_curator.grouping import image_quality_components, image_quality_score
from lora_dataset_curator.models import DuplicateGroup, ImageRecord
from lora_dataset_curator.scanner import scan_dataset
from lora_dataset_curator.storage import (
    ensure_app_data_dirs,
    load_default_profile,
    load_settings,
    save_settings,
)
from lora_dataset_curator.trash import empty_trash, restore_trash

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
        self.crop_rect: tuple[int, int, int, int] | None = None
        self.crop_edit_enabled = False
        self.crop_drag_handle: tuple[str, ...] | None = None
        self.crop_drag_rect: tuple[int, int, int, int] | None = None
        self.crop_changed_callback: Callable[[tuple[int, int, int, int]], None] | None = None
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

    def set_crop_rect(self, crop_rect: tuple[int, int, int, int] | None) -> None:
        self.crop_rect = crop_rect
        self.update()

    def set_crop_edit_enabled(self, enabled: bool) -> None:
        self.crop_edit_enabled = enabled
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_crop_changed_callback(
        self,
        callback: Callable[[tuple[int, int, int, int]], None] | None,
    ) -> None:
        self.crop_changed_callback = callback

    def clear(self) -> None:
        self.pixmap = QPixmap()
        self.crop_rect = None
        self.crop_drag_handle = None
        self.crop_drag_rect = None
        self.message = "선택된 이미지 없음"
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().mid().color())
        border_rect = self.rect().adjusted(1, 1, -2, -2)
        painter.drawRect(border_rect)

        content_rect = border_rect.adjusted(10, 10, -10, -10)
        if self.pixmap.isNull():
            painter.setPen(self.palette().text().color())
            painter.drawText(content_rect, Qt.AlignmentFlag.AlignCenter, self.message)
            return

        x, y, scaled_width, scaled_height = self.image_display_rect()
        scaled = self.pixmap.scaled(
            QSize(scaled_width, scaled_height),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(x, y, scaled)
        if self.effective_crop_rect() is not None:
            self.draw_crop_overlay(painter, x, y, scaled_width, scaled_height)

    def image_display_rect(self) -> tuple[int, int, int, int]:
        if self.pixmap.isNull():
            return (0, 0, 0, 0)
        border_rect = self.rect().adjusted(1, 1, -2, -2)
        content_rect = border_rect.adjusted(10, 10, -10, -10)
        scaled_size = self.pixmap.size()
        scaled_size.scale(content_rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = content_rect.x() + (content_rect.width() - scaled_size.width()) // 2
        y = content_rect.y() + (content_rect.height() - scaled_size.height()) // 2
        return (x, y, scaled_size.width(), scaled_size.height())

    def effective_crop_rect(self) -> tuple[int, int, int, int] | None:
        if self.pixmap.isNull():
            return None
        if self.crop_rect is not None:
            return self.crop_rect
        if self.crop_edit_enabled:
            return (0, 0, self.pixmap.width(), self.pixmap.height())
        return None

    def draw_crop_overlay(
        self,
        painter: QPainter,
        image_x: int,
        image_y: int,
        image_width: int,
        image_height: int,
    ) -> None:
        crop_rect = self.effective_crop_rect()
        if self.pixmap.isNull() or crop_rect is None:
            return
        crop_x, crop_y, crop_width, crop_height = crop_rect
        scale_x = image_width / self.pixmap.width()
        scale_y = image_height / self.pixmap.height()
        rect_x = image_x + int(crop_x * scale_x)
        rect_y = image_y + int(crop_y * scale_y)
        rect_width = max(1, int(crop_width * scale_x))
        rect_height = max(1, int(crop_height * scale_y))

        painter.save()
        overlay = QColor(0, 0, 0, 90)
        painter.fillRect(image_x, image_y, image_width, max(0, rect_y - image_y), overlay)
        painter.fillRect(
            image_x,
            rect_y + rect_height,
            image_width,
            max(0, image_y + image_height - (rect_y + rect_height)),
            overlay,
        )
        painter.fillRect(image_x, rect_y, max(0, rect_x - image_x), rect_height, overlay)
        painter.fillRect(
            rect_x + rect_width,
            rect_y,
            max(0, image_x + image_width - (rect_x + rect_width)),
            rect_height,
            overlay,
        )
        painter.setPen(QPen(QColor("#22c55e"), 3))
        painter.drawRect(rect_x, rect_y, rect_width, rect_height)
        if self.crop_edit_enabled:
            self.draw_crop_handles(painter, rect_x, rect_y, rect_width, rect_height)
        painter.restore()

    def draw_crop_handles(
        self,
        painter: QPainter,
        rect_x: int,
        rect_y: int,
        rect_width: int,
        rect_height: int,
    ) -> None:
        handle_size = 10
        points = (
            (rect_x, rect_y),
            (rect_x + rect_width // 2, rect_y),
            (rect_x + rect_width, rect_y),
            (rect_x, rect_y + rect_height // 2),
            (rect_x + rect_width, rect_y + rect_height // 2),
            (rect_x, rect_y + rect_height),
            (rect_x + rect_width // 2, rect_y + rect_height),
            (rect_x + rect_width, rect_y + rect_height),
        )
        painter.setPen(QPen(QColor("#16a34a"), 2))
        painter.setBrush(QColor("#ffffff"))
        for x, y in points:
            painter.drawRect(
                x - handle_size // 2,
                y - handle_size // 2,
                handle_size,
                handle_size,
            )

    def map_widget_to_image(self, point) -> tuple[int, int] | None:
        if self.pixmap.isNull():
            return None
        image_x, image_y, image_width, image_height = self.image_display_rect()
        if image_width <= 0 or image_height <= 0:
            return None
        x = max(image_x, min(point.x(), image_x + image_width - 1))
        y = max(image_y, min(point.y(), image_y + image_height - 1))
        if x <= image_x:
            mapped_x = 0
        elif x >= image_x + image_width - 1:
            mapped_x = self.pixmap.width() - 1
        else:
            mapped_x = round((x - image_x) * (self.pixmap.width() - 1) / max(1, image_width - 1))
        if y <= image_y:
            mapped_y = 0
        elif y >= image_y + image_height - 1:
            mapped_y = self.pixmap.height() - 1
        else:
            mapped_y = round(
                (y - image_y) * (self.pixmap.height() - 1) / max(1, image_height - 1)
            )
        return (
            max(0, min(mapped_x, self.pixmap.width() - 1)),
            max(0, min(mapped_y, self.pixmap.height() - 1)),
        )

    def display_crop_rect(self) -> tuple[int, int, int, int] | None:
        crop_rect = self.effective_crop_rect()
        if self.pixmap.isNull() or crop_rect is None:
            return None
        image_x, image_y, image_width, image_height = self.image_display_rect()
        if image_width <= 0 or image_height <= 0:
            return None
        crop_x, crop_y, crop_width, crop_height = crop_rect
        scale_x = image_width / self.pixmap.width()
        scale_y = image_height / self.pixmap.height()
        return (
            image_x + int(crop_x * scale_x),
            image_y + int(crop_y * scale_y),
            max(1, int(crop_width * scale_x)),
            max(1, int(crop_height * scale_y)),
        )

    def crop_handle_at(self, point) -> tuple[str, ...] | None:
        display_rect = self.display_crop_rect()
        if display_rect is None:
            return None
        rect_x, rect_y, rect_width, rect_height = display_rect
        x = point.x()
        y = point.y()
        right = rect_x + rect_width
        bottom = rect_y + rect_height
        threshold = 14
        near_left = abs(x - rect_x) <= threshold and rect_y - threshold <= y <= bottom + threshold
        near_right = abs(x - right) <= threshold and rect_y - threshold <= y <= bottom + threshold
        near_top = abs(y - rect_y) <= threshold and rect_x - threshold <= x <= right + threshold
        near_bottom = abs(y - bottom) <= threshold and rect_x - threshold <= x <= right + threshold

        if near_left and near_top:
            return ("left", "top")
        if near_right and near_top:
            return ("right", "top")
        if near_left and near_bottom:
            return ("left", "bottom")
        if near_right and near_bottom:
            return ("right", "bottom")
        if near_left:
            return ("left",)
        if near_right:
            return ("right",)
        if near_top:
            return ("top",)
        if near_bottom:
            return ("bottom",)
        return None

    def cursor_for_handle(self, handle: tuple[str, ...] | None) -> Qt.CursorShape:
        if handle in {("left", "top"), ("right", "bottom")}:
            return Qt.CursorShape.SizeFDiagCursor
        if handle in {("right", "top"), ("left", "bottom")}:
            return Qt.CursorShape.SizeBDiagCursor
        if handle in {("left",), ("right",)}:
            return Qt.CursorShape.SizeHorCursor
        if handle in {("top",), ("bottom",)}:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def update_handle_drag(self, point) -> None:
        if self.crop_drag_handle is None or self.crop_drag_rect is None:
            return
        mapped = self.map_widget_to_image(point)
        if mapped is None:
            return
        image_width = self.pixmap.width()
        image_height = self.pixmap.height()
        x, y, width, height = self.crop_drag_rect
        left = x
        top = y
        right = x + width - 1
        bottom = y + height - 1
        pointer_x, pointer_y = mapped
        if "left" in self.crop_drag_handle:
            left = max(0, min(pointer_x, right))
        if "right" in self.crop_drag_handle:
            right = min(image_width - 1, max(pointer_x, left))
        if "top" in self.crop_drag_handle:
            top = max(0, min(pointer_y, bottom))
        if "bottom" in self.crop_drag_handle:
            bottom = min(image_height - 1, max(pointer_y, top))
        crop_rect = (left, top, max(1, right - left + 1), max(1, bottom - top + 1))
        self.set_crop_rect(crop_rect)
        if self.crop_changed_callback is not None:
            self.crop_changed_callback(crop_rect)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.crop_edit_enabled and event.button() == Qt.MouseButton.LeftButton:
            handle = self.crop_handle_at(event.position().toPoint())
            if handle is not None and self.effective_crop_rect() is not None:
                self.crop_drag_handle = handle
                self.crop_drag_rect = self.effective_crop_rect()
                self.setCursor(self.cursor_for_handle(handle))
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.crop_edit_enabled and self.crop_drag_handle is not None:
            self.update_handle_drag(event.position().toPoint())
            return
        if self.crop_edit_enabled:
            self.setCursor(self.cursor_for_handle(self.crop_handle_at(event.position().toPoint())))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.crop_edit_enabled and event.button() == Qt.MouseButton.LeftButton:
            self.update_handle_drag(event.position().toPoint())
            self.crop_drag_handle = None
            self.crop_drag_rect = None
            self.setCursor(self.cursor_for_handle(self.crop_handle_at(event.position().toPoint())))
            return
        super().mouseReleaseEvent(event)


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
        components = image_quality_components(record)
        file_size = format_file_size(record.file_size or 0)
        self.meta_label.setText(
            f"score {image_quality_score(record)} | {size} | {file_size} | "
            f"tags {components['tags']} | {decision_label} | {', '.join(sidecars)}"
        )


class FloatingPreviewWindow(QWidget):
    THUMBNAIL_SIZE = 96
    THUMBNAIL_PRELOAD_RADIUS = 12

    def __init__(self, owner: MainWindow) -> None:
        super().__init__(
            owner,
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.owner = owner
        self.setWindowTitle("이미지 검수")
        self.resize(1080, 900)
        self.thumbnail_records: list[ImageRecord] = []
        self.loaded_thumbnail_paths: set[Path] = set()
        self.syncing_thumbnails = False
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setFixedWidth(190)
        self.thumbnail_list.setIconSize(QSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE))
        self.thumbnail_list.currentRowChanged.connect(self.on_thumbnail_row_changed)

        self.preview = ImagePreview(
            minimum_width=640,
            minimum_height=640,
            maximum_height=16777215,
        )
        self.preview.set_crop_edit_enabled(True)
        self.preview.set_crop_changed_callback(self.owner.set_current_crop_rect)
        self.always_on_top_checkbox = QCheckBox("항상 위")
        self.always_on_top_checkbox.setChecked(True)
        self.always_on_top_checkbox.toggled.connect(self.set_always_on_top)
        self.filename_label = QLabel("선택된 이미지 없음")
        self.filename_label.setWordWrap(True)
        self.filename_label.setFixedHeight(48)
        self.filename_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        info_panel = QWidget()
        info_layout = QGridLayout(info_panel)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setHorizontalSpacing(12)
        info_layout.setColumnMinimumWidth(0, 72)
        self.resolution_value = self.add_preview_info_row(info_layout, 0, "해상도", "-")
        self.file_size_value = self.add_preview_info_row(info_layout, 1, "용량", "-")
        self.file_type_value = self.add_preview_info_row(info_layout, 2, "형식", "-")
        self.decision_value = self.add_preview_info_row(info_layout, 3, "현재 결정", "-")

        self.guide_label = QLabel(
            "드래그: 자를 뒤 남길 영역 지정 | ←/→ 또는 ↑/↓ 이동 | "
            "A 이동 결정 | D 삭제 예정 | S 보류"
        )
        self.guide_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guide_label.setWordWrap(True)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        detail_layout.addWidget(
            self.always_on_top_checkbox,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        detail_layout.addWidget(self.preview, stretch=1)
        detail_layout.addWidget(self.filename_label)
        detail_layout.addWidget(info_panel)
        detail_layout.addWidget(self.guide_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.thumbnail_list)
        layout.addWidget(detail_panel, stretch=1)
        self.create_shortcuts()

    def set_always_on_top(self, enabled: bool) -> None:
        flags = Qt.WindowType.Window
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        geometry = self.geometry()
        self.setWindowFlags(flags)
        self.setGeometry(geometry)
        if was_visible:
            self.show()
            self.raise_()
            self.activateWindow()

    @staticmethod
    def add_preview_info_row(
        layout: QGridLayout,
        row: int,
        title: str,
        value: str,
    ) -> QLabel:
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label = QLabel(value)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(title_label, row, 0)
        layout.addWidget(value_label, row, 1)
        return value_label

    def refresh_thumbnail_list(self) -> None:
        records = self.owner.records
        if [record.image_path for record in records] == [
            record.image_path for record in self.thumbnail_records
        ]:
            return

        self.syncing_thumbnails = True
        self.thumbnail_list.clear()
        self.thumbnail_records = list(records)
        self.loaded_thumbnail_paths.clear()
        for record in self.thumbnail_records:
            item = QListWidgetItem(record.image_path.name)
            item.setToolTip(str(record.image_path))
            self.thumbnail_list.addItem(item)
        self.syncing_thumbnails = False

    @staticmethod
    def make_thumbnail(path: Path) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image_size = reader.size()
        target_size = QSize(
            FloatingPreviewWindow.THUMBNAIL_SIZE,
            FloatingPreviewWindow.THUMBNAIL_SIZE,
        )
        if image_size.isValid():
            image_size.scale(target_size, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(image_size)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image).scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def load_nearby_thumbnails(self, center_row: int) -> None:
        if center_row < 0:
            return
        first_row = max(0, center_row - self.THUMBNAIL_PRELOAD_RADIUS)
        last_row = min(len(self.thumbnail_records), center_row + self.THUMBNAIL_PRELOAD_RADIUS + 1)
        self.thumbnail_list.setUpdatesEnabled(False)
        try:
            for row in range(first_row, last_row):
                record = self.thumbnail_records[row]
                if record.image_path in self.loaded_thumbnail_paths:
                    continue
                item = self.thumbnail_list.item(row)
                if item is None:
                    continue
                thumbnail = self.make_thumbnail(record.image_path)
                if not thumbnail.isNull():
                    item.setIcon(QIcon(thumbnail))
                self.loaded_thumbnail_paths.add(record.image_path)
        finally:
            self.thumbnail_list.setUpdatesEnabled(True)

    def sync_thumbnail_selection(self, record: ImageRecord | None) -> None:
        self.refresh_thumbnail_list()
        if record is None:
            return
        row = next(
            (
                index
                for index, candidate in enumerate(self.thumbnail_records)
                if candidate.image_path == record.image_path
            ),
            -1,
        )
        if row < 0:
            return
        self.load_nearby_thumbnails(row)
        self.syncing_thumbnails = True
        self.thumbnail_list.setCurrentRow(row)
        item = self.thumbnail_list.item(row)
        if item is not None:
            self.thumbnail_list.scrollToItem(item)
        self.syncing_thumbnails = False

    def on_thumbnail_row_changed(self, row: int) -> None:
        if self.syncing_thumbnails or row < 0 or row >= len(self.thumbnail_records):
            return
        self.load_nearby_thumbnails(row)
        self.owner.select_record(self.thumbnail_records[row])

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
        self.sync_thumbnail_selection(record)
        if record is None:
            self.preview.clear()
            self.filename_label.setText("선택된 이미지 없음")
            self.filename_label.setToolTip("")
            self.resolution_value.setText("-")
            self.file_size_value.setText("-")
            self.file_type_value.setText("-")
            self.decision_value.setText("-")
            return
        self.preview.set_image(record.image_path)
        self.preview.set_crop_rect(self.owner.crop_rects.get(str(record.image_path)))
        decision = self.owner.review_decisions.get(str(record.image_path), "")
        label = DECISION_LABELS.get(decision, "미결정")
        size = f"{record.width}x{record.height}" if record.width and record.height else "unknown"
        file_type = record.image_path.suffix.lstrip(".").upper() or "unknown"
        self.filename_label.setText(record.image_path.name)
        self.filename_label.setToolTip(record.image_path.name)
        self.resolution_value.setText(size)
        self.file_size_value.setText(format_file_size(record.file_size or 0))
        self.file_type_value.setText(file_type)
        self.decision_value.setText(label)

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
        self.crop_rects: dict[str, tuple[int, int, int, int]] = {}
        self.syncing_crop_controls = False
        self.current_record: ImageRecord | None = None
        self.duplicate_result: DuplicateAnalysisResult | None = None
        self.background_tasks = background_tasks
        self.active_thread: QThread | None = None
        self.active_worker: TaskWorker | None = None
        self.floating_preview: FloatingPreviewWindow | None = None
        self.app_paths = ensure_app_data_dirs()
        self.settings = load_settings()
        self.profile = load_default_profile()

        self.setWindowTitle("LoRA Dataset Curator")
        self.resize(1280, 800)

        initial_input_dir = input_dir or self.path_setting("last_input_dir")
        initial_output_dir = (
            output_dir
            or self.path_setting("last_output_dir")
            or Path.cwd() / "output"
        )
        self.input_path = QLineEdit(str(initial_input_dir) if initial_input_dir else "")
        self.output_path = QLineEdit(str(initial_output_dir))
        self.crop_rects = load_crop_settings(self.output_root())
        self.summary_label = QLabel("아직 스캔하지 않았습니다.")
        self.status_label = QLabel("대기 중")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.preview_label = ImagePreview()

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["그룹", "점수", "결정", "파일", "크기", "캡션", "메타데이터"]
        )
        self.configure_interactive_header(
            self.table,
            [72, 72, 96, 360, 110, 80, 100],
        )
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
        self.crop_enabled_checkbox = QCheckBox("자르기 적용")
        self.crop_enabled_checkbox.toggled.connect(self.on_crop_controls_changed)
        self.crop_left = self.create_crop_spinbox()
        self.crop_top = self.create_crop_spinbox()
        self.crop_right = self.create_crop_spinbox()
        self.crop_bottom = self.create_crop_spinbox()
        self.crop_square_button = QPushButton("중앙 정사각형")
        self.crop_square_button.clicked.connect(self.set_center_square_crop)
        self.crop_full_button = QPushButton("전체")
        self.crop_full_button.clicked.connect(self.clear_current_crop)
        self.batch_crop_left = self.create_crop_ratio_spinbox()
        self.batch_crop_top = self.create_crop_ratio_spinbox()
        self.batch_crop_right = self.create_crop_ratio_spinbox()
        self.batch_crop_bottom = self.create_crop_ratio_spinbox()
        self.batch_crop_button = QPushButton("비율 일괄 적용")
        self.batch_crop_button.clicked.connect(self.apply_batch_crop_ratios)
        self.duplicate_summary_label = QLabel("아직 중복 분석을 실행하지 않았습니다.")
        self.use_perceptual_checkbox = QCheckBox("pHash/dHash 사용")
        duplicate_settings = self.profile.get("duplicates", {})
        if not isinstance(duplicate_settings, dict):
            duplicate_settings = {}
        self.use_perceptual_checkbox.setChecked(
            bool(duplicate_settings.get("use_perceptual", True))
        )
        self.phash_threshold = QSpinBox()
        self.phash_threshold.setRange(0, 64)
        self.phash_threshold.setValue(int(duplicate_settings.get("phash_threshold", 6)))
        self.dhash_threshold = QSpinBox()
        self.dhash_threshold.setRange(0, 64)
        self.dhash_threshold.setValue(int(duplicate_settings.get("dhash_threshold", 6)))

        self.group_table = QTableWidget(0, 5)
        self.group_table.setHorizontalHeaderLabels(
            ["그룹", "개수", "추천 점수", "이유", "추천 keep"]
        )
        self.configure_interactive_header(self.group_table, [80, 70, 90, 220, 260])
        self.group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_table.itemSelectionChanged.connect(self.on_group_selection_changed)

        self.group_member_table = QTableWidget(0, 7)
        self.group_member_table.setHorizontalHeaderLabels(
            ["추천", "점수", "결정", "파일", "크기", "캡션", "메타데이터"]
        )
        self.configure_interactive_header(
            self.group_member_table,
            [70, 72, 96, 360, 110, 80, 100],
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

    def path_setting(self, key: str) -> Path | None:
        value = self.settings.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return Path(value).expanduser()

    def create_crop_spinbox(self, *, minimum: int = 0) -> QSpinBox:
        spinbox = QSpinBox()
        spinbox.setRange(minimum, 999_999)
        spinbox.valueChanged.connect(self.on_crop_controls_changed)
        return spinbox

    @staticmethod
    def create_crop_ratio_spinbox() -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 99.9)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(0.5)
        spinbox.setSuffix("%")
        return spinbox

    def save_current_paths(self) -> None:
        updates: dict[str, str] = {}
        input_text = self.input_path.text().strip()
        output_text = self.output_path.text().strip()
        if input_text:
            updates["last_input_dir"] = str(Path(input_text).expanduser())
        if output_text:
            updates["last_output_dir"] = str(Path(output_text).expanduser())
        if not updates:
            return
        save_settings(updates)
        self.settings = load_settings()

    @staticmethod
    def configure_interactive_header(table: QTableWidget, widths: list[int]) -> None:
        table.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        header = table.horizontalHeader()
        header.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        header.setStretchLastSection(False)
        header.setSectionsMovable(False)
        for column, width in enumerate(widths):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(column, width)

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
        preview_layout.setContentsMargins(12, 12, 12, 6)
        preview_layout.addWidget(self.preview_label, stretch=1)
        preview_layout.addLayout(self.build_action_buttons())
        preview_layout.addWidget(self.build_crop_controls())

        caption_panel = QWidget()
        caption_layout = QVBoxLayout(caption_panel)
        caption_layout.setContentsMargins(12, 6, 12, 6)
        caption_layout.addWidget(QLabel("캡션"))
        caption_layout.addWidget(self.caption_text)
        caption_layout.addWidget(self.caption_meta_label)

        info_panel = self.build_collapsible_text_panel("파일 정보", self.info_text)
        metadata_panel = self.build_collapsible_text_panel("메타데이터", self.metadata_text)

        self.review_detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.review_detail_splitter.setChildrenCollapsible(False)
        for panel in (preview_panel, caption_panel, info_panel, metadata_panel):
            self.review_detail_splitter.addWidget(panel)
        self.review_detail_splitter.setSizes([320, 260, 44, 44])

        self.review_splitter = QSplitter()
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.addWidget(left)
        self.review_splitter.addWidget(self.review_detail_splitter)
        self.review_splitter.setStretchFactor(0, 3)
        self.review_splitter.setStretchFactor(1, 2)
        self.review_splitter.setSizes([760, 520])
        return self.review_splitter

    def build_crop_controls(self) -> QWidget:
        panel = QGroupBox("자르기")
        layout = QGridLayout(panel)
        layout.addWidget(self.crop_enabled_checkbox, 0, 0)
        layout.addWidget(QLabel("왼쪽"), 0, 1)
        layout.addWidget(self.crop_left, 0, 2)
        layout.addWidget(QLabel("위"), 0, 3)
        layout.addWidget(self.crop_top, 0, 4)
        layout.addWidget(QLabel("오른쪽"), 1, 1)
        layout.addWidget(self.crop_right, 1, 2)
        layout.addWidget(QLabel("아래"), 1, 3)
        layout.addWidget(self.crop_bottom, 1, 4)
        layout.addWidget(self.crop_square_button, 0, 5)
        layout.addWidget(self.crop_full_button, 1, 5)
        layout.addWidget(QLabel("일괄 비율"), 2, 0)
        layout.addWidget(QLabel("왼쪽"), 2, 1)
        layout.addWidget(self.batch_crop_left, 2, 2)
        layout.addWidget(QLabel("위"), 2, 3)
        layout.addWidget(self.batch_crop_top, 2, 4)
        layout.addWidget(QLabel("오른쪽"), 3, 1)
        layout.addWidget(self.batch_crop_right, 3, 2)
        layout.addWidget(QLabel("아래"), 3, 3)
        layout.addWidget(self.batch_crop_bottom, 3, 4)
        layout.addWidget(self.batch_crop_button, 2, 5, 2, 1)
        layout.setColumnStretch(6, 1)
        return panel

    @staticmethod
    def build_collapsible_text_panel(title: str, text_widget: QPlainTextEdit) -> QGroupBox:
        panel = QGroupBox(title)
        panel.setCheckable(True)
        panel.setChecked(False)
        text_widget.setVisible(False)
        layout = QVBoxLayout(panel)
        layout.addWidget(text_widget)
        panel.toggled.connect(text_widget.setVisible)
        return panel

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
        self.apply_recommendations_button = QPushButton("추천/비중복 이동 등록")
        self.apply_recommendations_button.clicked.connect(self.apply_recommended_decisions)

        controls_widget = QWidget()
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.prepare_cache_button)
        controls.addWidget(self.apply_recommendations_button)
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

        restore_trash_action = QAction("휴지통 복구", self)
        restore_trash_action.triggered.connect(self.restore_trash_items)
        file_menu.addAction(restore_trash_action)

        empty_trash_action = QAction("휴지통 비우기", self)
        empty_trash_action.triggered.connect(self.empty_trash_items)
        file_menu.addAction(empty_trash_action)

        file_menu.addSeparator()

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

    def restore_trash_items(self) -> None:
        result = restore_trash()
        message = (
            f"휴지통 복구: {result.restored_files}개 복구, "
            f"{result.skipped_files}개 건너뜀"
        )
        self.status_label.setText(message)
        QMessageBox.information(self, "휴지통 복구", message)
        input_root = Path(self.input_path.text()).expanduser()
        if input_root.exists():
            self.scan()

    def empty_trash_items(self) -> None:
        answer = QMessageBox.question(
            self,
            "휴지통 비우기",
            "휴지통의 파일을 영구 삭제합니다. 계속할까요?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = empty_trash()
        message = f"휴지통 비우기: {result.deleted_entries}개 항목 삭제"
        self.status_label.setText(message)
        QMessageBox.information(self, "휴지통 비우기", message)

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
            self.save_current_paths()

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "출력 폴더 선택",
            self.output_path.text(),
        )
        if path:
            self.output_path.setText(QDir.toNativeSeparators(path))
            self.save_current_paths()
            self.crop_rects = load_crop_settings(self.output_root())
            self.sync_crop_controls(self.current_record)

    def scan(self) -> None:
        input_dir = Path(self.input_path.text()).expanduser()
        if not input_dir.exists():
            QMessageBox.warning(
                self,
                "스캔 실패",
                f"입력 폴더가 없습니다:\n{input_dir}",
            )
            return

        self.save_current_paths()
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
        self.crop_rects = load_crop_settings(self.output_root())

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
                str(image_quality_score(record)),
                DECISION_LABELS.get(self.review_decisions.get(str(record.image_path), ""), ""),
                record.image_path.name,
                size,
                "yes" if record.caption_path else "no",
                "yes" if record.metadata_path else "no",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 1:
                    item.setToolTip(format_quality_details(record))
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
        self.caption_text.setPlainText(record.caption_text)
        self.caption_meta_label.setText(self.format_caption_meta(record))
        self.metadata_text.setPlainText(
            json.dumps(record.raw_metadata, ensure_ascii=False, indent=2)
            if record.raw_metadata
            else "{}"
        )
        self.info_text.setPlainText(self.format_info(record))
        self.load_preview(record.image_path)
        self.sync_crop_controls(record)
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.show_record(record)

    def clear_details(self) -> None:
        self.current_record = None
        self.preview_label.clear()
        self.caption_text.clear()
        self.caption_meta_label.clear()
        self.metadata_text.clear()
        self.info_text.clear()
        self.sync_crop_controls(None)

    def load_preview(self, path: Path) -> None:
        self.preview_label.set_image(path)
        crop_rect = (
            self.crop_rects.get(str(self.current_record.image_path))
            if self.current_record is not None
            else None
        )
        self.preview_label.set_crop_rect(crop_rect)

    def sync_crop_controls(self, record: ImageRecord | None) -> None:
        self.syncing_crop_controls = True
        try:
            enabled = record is not None and record.width is not None and record.height is not None
            for widget in (
                self.crop_enabled_checkbox,
                self.crop_left,
                self.crop_top,
                self.crop_right,
                self.crop_bottom,
                self.crop_square_button,
                self.crop_full_button,
            ):
                widget.setEnabled(enabled)

            if not enabled or record is None:
                self.crop_enabled_checkbox.setChecked(False)
                self.preview_label.set_crop_rect(None)
                return

            width = record.width or 1
            height = record.height or 1
            self.crop_left.setRange(0, max(0, width - 1))
            self.crop_right.setRange(0, max(0, width - 1))
            self.crop_top.setRange(0, max(0, height - 1))
            self.crop_bottom.setRange(0, max(0, height - 1))

            crop_rect = self.crop_rects.get(str(record.image_path))
            if crop_rect is None:
                self.crop_enabled_checkbox.setChecked(False)
                self.crop_left.setValue(0)
                self.crop_top.setValue(0)
                self.crop_right.setValue(0)
                self.crop_bottom.setValue(0)
            else:
                crop_rect = self.clamp_crop_rect(record, crop_rect)
                left, top, right, bottom = self.crop_margins_from_rect(record, crop_rect)
                self.crop_enabled_checkbox.setChecked(True)
                self.crop_left.setValue(left)
                self.crop_top.setValue(top)
                self.crop_right.setValue(right)
                self.crop_bottom.setValue(bottom)
            self.preview_label.set_crop_rect(crop_rect)
        finally:
            self.syncing_crop_controls = False

    @staticmethod
    def clamp_crop_rect(
        record: ImageRecord,
        crop_rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        width = record.width or 1
        height = record.height or 1
        x, y, crop_width, crop_height = crop_rect
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        crop_width = max(1, min(crop_width, width - x))
        crop_height = max(1, min(crop_height, height - y))
        return (x, y, crop_width, crop_height)

    @staticmethod
    def crop_margins_from_rect(
        record: ImageRecord,
        crop_rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        width = record.width or 1
        height = record.height or 1
        x, y, crop_width, crop_height = MainWindow.clamp_crop_rect(record, crop_rect)
        return (x, y, max(0, width - x - crop_width), max(0, height - y - crop_height))

    @staticmethod
    def crop_rect_from_margins(
        record: ImageRecord,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> tuple[int, int, int, int]:
        width = record.width or 1
        height = record.height or 1
        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(0, min(right, width - left - 1))
        bottom = max(0, min(bottom, height - top - 1))
        return (left, top, width - left - right, height - top - bottom)

    @staticmethod
    def crop_rect_from_ratio_margins(
        record: ImageRecord,
        left_percent: float,
        top_percent: float,
        right_percent: float,
        bottom_percent: float,
    ) -> tuple[int, int, int, int]:
        width = record.width or 1
        height = record.height or 1
        left = round(width * left_percent / 100)
        top = round(height * top_percent / 100)
        right = round(width * right_percent / 100)
        bottom = round(height * bottom_percent / 100)
        return MainWindow.crop_rect_from_margins(record, left, top, right, bottom)

    @staticmethod
    def is_full_crop_rect(record: ImageRecord, crop_rect: tuple[int, int, int, int]) -> bool:
        x, y, crop_width, crop_height = MainWindow.clamp_crop_rect(record, crop_rect)
        return x == 0 and y == 0 and crop_width == (record.width or 1) and crop_height == (
            record.height or 1
        )

    def on_crop_controls_changed(self) -> None:
        if self.syncing_crop_controls or self.current_record is None:
            return

        key = str(self.current_record.image_path)
        if not self.crop_enabled_checkbox.isChecked():
            self.crop_rects.pop(key, None)
            self.save_crop_rects()
            self.preview_label.set_crop_rect(None)
            if self.floating_preview is not None and self.floating_preview.isVisible():
                self.floating_preview.show_record(self.current_record)
            return

        crop_rect = self.crop_rect_from_margins(
            self.current_record,
            self.crop_left.value(),
            self.crop_top.value(),
            self.crop_right.value(),
            self.crop_bottom.value(),
        )
        if self.is_full_crop_rect(self.current_record, crop_rect):
            self.crop_rects.pop(key, None)
            self.save_crop_rects()
            self.preview_label.set_crop_rect(None)
            if self.floating_preview is not None and self.floating_preview.isVisible():
                self.floating_preview.preview.set_crop_rect(None)
            return
        self.set_current_crop_rect(crop_rect)

    def set_center_square_crop(self) -> None:
        if (
            self.current_record is None
            or not self.current_record.width
            or not self.current_record.height
        ):
            return
        side = min(self.current_record.width, self.current_record.height)
        x = (self.current_record.width - side) // 2
        y = (self.current_record.height - side) // 2
        self.set_current_crop_rect((x, y, side, side))

    def apply_batch_crop_ratios(self) -> None:
        if not self.records:
            self.status_label.setText("스캔된 이미지가 없습니다.")
            return

        left_percent = self.batch_crop_left.value()
        top_percent = self.batch_crop_top.value()
        right_percent = self.batch_crop_right.value()
        bottom_percent = self.batch_crop_bottom.value()
        applied = 0
        cleared = 0
        skipped = 0
        for record in self.records:
            if not record.width or not record.height:
                skipped += 1
                continue
            key = str(record.image_path)
            crop_rect = self.crop_rect_from_ratio_margins(
                record,
                left_percent,
                top_percent,
                right_percent,
                bottom_percent,
            )
            if self.is_full_crop_rect(record, crop_rect):
                if key in self.crop_rects:
                    cleared += 1
                self.crop_rects.pop(key, None)
                continue
            self.crop_rects[key] = crop_rect
            applied += 1

        self.save_crop_rects()
        self.sync_crop_controls(self.current_record)
        self.update_preview()
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.show_record(self.current_record)
        message = f"일괄 자르기 설정: {applied}개 적용"
        if cleared:
            message += f", {cleared}개 해제"
        if skipped:
            message += f", {skipped}개 건너뜀"
        self.status_label.setText(message)

    def clear_current_crop(self) -> None:
        if self.current_record is None:
            return
        key = str(self.current_record.image_path)
        self.crop_rects.pop(key, None)
        self.save_crop_rects()
        self.sync_crop_controls(self.current_record)
        self.preview_label.set_crop_rect(None)
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.preview.set_crop_rect(None)

    def set_current_crop_rect(self, crop_rect: tuple[int, int, int, int]) -> None:
        if self.current_record is None:
            return
        crop_rect = self.clamp_crop_rect(self.current_record, crop_rect)
        if self.is_full_crop_rect(self.current_record, crop_rect):
            self.clear_current_crop()
            return
        self.crop_rects[str(self.current_record.image_path)] = crop_rect
        self.save_crop_rects()
        self.preview_label.set_crop_rect(crop_rect)
        self.sync_crop_controls(self.current_record)
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.preview.set_crop_rect(crop_rect)

    def save_crop_rects(self) -> None:
        save_crop_settings(self.output_root(), self.crop_rects)

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

    def apply_recommended_decisions(self) -> None:
        if self.duplicate_result is None:
            QMessageBox.information(
                self,
                "추천 결정 등록",
                "먼저 중복 그룹 분석을 실행하세요.",
            )
            return

        grouped_paths: set[Path] = set()
        recommended_paths: set[Path] = set()
        for group in self.duplicate_result.groups:
            grouped_paths.update(record.image_path for record in group.images)
            if group.recommended_keep is not None:
                recommended_paths.add(group.recommended_keep.image_path)

        move_count = 0
        skip_count = 0
        for record in self.records:
            action = (
                "move"
                if record.image_path in recommended_paths or record.image_path not in grouped_paths
                else "skip"
            )
            self.review_decisions[str(record.image_path)] = action
            record.review_status = action
            if action == "move":
                move_count += 1
            else:
                skip_count += 1

        save_decisions(self.output_root(), self.review_decisions)
        self.populate_table()
        if self.current_record is not None:
            self.select_record(self.current_record)
        self.refresh_current_group_members()
        if self.floating_preview is not None and self.floating_preview.isVisible():
            self.floating_preview.show_record(self.current_record)
        self.status_label.setText(
            f"추천/비중복 이동 {move_count}개, 보류 {skip_count}개로 등록했습니다."
        )

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
            crop_rect = (
                self.crop_rects.get(str(record.image_path))
                if action == "move"
                else None
            )
            execute_plan(plan, crop_rect=crop_rect)
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
            keep_score = (
                image_quality_score(group.recommended_keep)
                if group.recommended_keep
                else 0
            )
            values = [group.group_id, str(len(group.images)), str(keep_score), reasons, keep]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 2 and group.recommended_keep is not None:
                    item.setToolTip(format_quality_details(group.recommended_keep))
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
                str(image_quality_score(record)),
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
                if column == 1:
                    item.setToolTip(format_quality_details(record))
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
                -image_quality_score(record),
                record != group.recommended_keep,
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
        self.apply_recommendations_button.setEnabled(not busy)
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

    def closeEvent(self, event) -> None:  # noqa: N802
        self.save_current_paths()
        super().closeEvent(event)

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
            f"점수: {image_quality_score(record)} | 결정: {decision} | {', '.join(sidecars)}"
        )

    @staticmethod
    def format_info(record: ImageRecord) -> str:
        lines = [
            f"경로: {record.image_path}",
            f"캡션: {record.caption_path or '없음'}",
            f"메타데이터: {record.metadata_path or '없음'}",
            f"해상도: {record.width or '?'}x{record.height or '?'}",
            f"파일 크기: {record.file_size or 0} bytes",
            f"MD5: {record.source_md5 or ''}",
            f"출처: {record.source_url or ''}",
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


def format_quality_details(record: ImageRecord) -> str:
    components = image_quality_components(record)
    size = f"{record.width}x{record.height}" if record.width and record.height else "unknown"
    return (
        f"점수: {image_quality_score(record)}\n"
        f"해상도: {size} ({components['resolution']:,} px)\n"
        f"용량: {format_file_size(components['file_size'])}\n"
        f"태그 수: {components['tags']}\n"
        f"메타데이터 항목: {components['metadata']}\n"
        f"캡션 길이: {components['caption']}"
    )


def run_gui(input_dir: Path | None = None, output_dir: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(input_dir=input_dir, output_dir=output_dir)
    window.show()
    return app.exec()
