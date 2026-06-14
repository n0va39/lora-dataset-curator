from __future__ import annotations

import os
import time

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtTest = pytest.importorskip("PySide6.QtTest")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from lora_dataset_curator.scanner import scan_dataset  # noqa: E402
from lora_dataset_curator.storage import (  # noqa: E402
    APP_HOME_ENV,
    ensure_app_data_dirs,
    load_settings,
    save_settings,
)
from lora_dataset_curator.ui import main_window as main_window_module  # noqa: E402
from lora_dataset_curator.ui.main_window import MainWindow  # noqa: E402


def test_main_window_scans_initial_dataset(tmp_path):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (16, 8)).save(image_path)
    (tmp_path / "sample.txt").write_text("caption", encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)

    assert app is not None
    assert len(window.records) == 1
    assert window.table.rowCount() == 1
    assert [
        window.table.horizontalHeaderItem(column).text()
        for column in range(window.table.columnCount())
    ] == ["그룹", "점수", "결정", "파일", "크기", "캡션", "메타데이터"]
    assert "이미지: 1" in window.summary_label.text()
    assert "캡션: 1개 연결, 0개 누락" in window.summary_label.text()
    assert window.use_perceptual_checkbox.isChecked()

    window.close()


def test_main_window_restores_and_saves_last_paths(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    next_input_dir = tmp_path / "next_input"
    next_output_dir = tmp_path / "next_output"
    input_dir.mkdir()
    output_dir.mkdir()

    save_settings(
        {
            "last_input_dir": str(input_dir),
            "last_output_dir": str(output_dir),
        }
    )

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(background_tasks=False)

    assert app is not None
    assert window.input_path.text() == str(input_dir)
    assert window.output_path.text() == str(output_dir)

    window.input_path.setText(str(next_input_dir))
    window.output_path.setText(str(next_output_dir))
    window.close()

    settings = load_settings()

    assert settings["last_input_dir"] == str(next_input_dir)
    assert settings["last_output_dir"] == str(next_output_dir)


def test_main_window_populates_duplicate_group_tab(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (16, 8), color="blue").save(tmp_path / "b.png")
    (tmp_path / "a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": 10}', encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.use_perceptual_checkbox.setChecked(False)
    window.analyze_duplicate_groups()

    assert app is not None
    assert window.group_table.rowCount() == 1
    assert window.group_member_table.rowCount() == 2
    assert window.group_preview_layout.count() == 2
    assert "그룹: 1" in window.duplicate_summary_label.text()

    window.close()


def test_duplicate_analysis_sorts_review_table_by_group(tmp_path):
    Image.new("RGB", (16, 8), color="green").save(tmp_path / "a_ungrouped.png")
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "z_group_a.png")
    Image.new("RGB", (16, 8), color="blue").save(tmp_path / "z_group_b.png")
    (tmp_path / "z_group_a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "z_group_b.json").write_text('{"id": 10}', encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.use_perceptual_checkbox.setChecked(False)
    window.analyze_duplicate_groups()

    assert app is not None
    assert window.table.item(0, 0).text() == "G0001"
    assert window.table.item(1, 0).text() == "G0001"
    assert window.table.item(2, 0).text() == ""
    assert window.table.item(2, 3).text() == "a_ungrouped.png"
    assert window.table.item(0, 0).data(QtCore.Qt.ItemDataRole.UserRole + 1) is True

    window.close()


def test_apply_recommended_decisions_moves_keep_and_ungrouped_records(tmp_path):
    Image.new("RGB", (16, 8), color="green").save(tmp_path / "a_ungrouped.png")
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "z_group_a.png")
    Image.new("RGB", (24, 16), color="blue").save(tmp_path / "z_group_b.png")
    (tmp_path / "z_group_a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "z_group_b.json").write_text('{"id": 10}', encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    output_dir = tmp_path / "out"
    window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    window.use_perceptual_checkbox.setChecked(False)
    window.analyze_duplicate_groups()
    window.set_current_decision("delete")

    window.apply_recommended_decisions()

    assert app is not None
    assert window.review_decisions[str(tmp_path / "a_ungrouped.png")] == "move"
    assert window.review_decisions[str(tmp_path / "z_group_b.png")] == "move"
    assert window.review_decisions[str(tmp_path / "z_group_a.png")] == "skip"
    assert "추천/비중복 이동 2개, 보류 1개" in window.status_label.text()

    next_window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)

    assert next_window.review_decisions[str(tmp_path / "a_ungrouped.png")] == "move"
    assert next_window.review_decisions[str(tmp_path / "z_group_b.png")] == "move"
    assert next_window.review_decisions[str(tmp_path / "z_group_a.png")] == "skip"

    window.close()
    next_window.close()


def test_review_decisions_are_saved_and_loaded(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    output_dir = tmp_path / "out"
    window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    window.set_current_decision("move")
    window.close()

    next_window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)

    assert app is not None
    assert next_window.review_decisions[str(tmp_path / "a.png")] == "move"
    assert next_window.table.item(0, 2).text() == "이동"

    next_window.close()


def test_crop_settings_are_saved_loaded_and_previewed(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (20, 12), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    output_dir = tmp_path / "out"
    window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    window.crop_enabled_checkbox.setChecked(True)
    window.crop_left.setValue(2)
    window.crop_top.setValue(3)
    window.crop_right.setValue(8)
    window.crop_bottom.setValue(3)
    window.close()

    next_window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)

    assert app is not None
    assert next_window.crop_rects[str(image_path)] == (2, 3, 10, 6)
    assert next_window.preview_label.crop_rect == (2, 3, 10, 6)
    assert next_window.crop_enabled_checkbox.isChecked()
    assert next_window.crop_left.value() == 2
    assert next_window.crop_top.value() == 3
    assert next_window.crop_right.value() == 8
    assert next_window.crop_bottom.value() == 3

    next_window.close()


def test_execute_review_decisions_applies_crop_to_moved_image(tmp_path, monkeypatch):
    image_path = tmp_path / "a.png"
    caption_path = tmp_path / "a.txt"
    Image.new("RGB", (20, 12), color="red").save(image_path)
    caption_path.write_text("caption", encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    output_dir = tmp_path / "out"
    window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    window.crop_enabled_checkbox.setChecked(True)
    window.crop_left.setValue(4)
    window.crop_top.setValue(2)
    window.crop_right.setValue(8)
    window.crop_bottom.setValue(5)
    window.set_current_decision("move")
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *args, **kwargs: None)

    window.execute_review_decisions()

    target_image = output_dir / "a.png"
    target_caption = output_dir / "a.txt"
    assert app is not None
    assert not image_path.exists()
    assert target_caption.read_text(encoding="utf-8") == "caption"
    with Image.open(target_image) as image:
        assert image.size == (8, 5)

    window.close()


def test_caption_meta_shows_size_and_file_size(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (16, 8), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)

    assert app is not None
    assert "크기: 16x8" in window.caption_meta_label.text()
    assert "용량:" in window.caption_meta_label.text()
    assert "점수:" in window.caption_meta_label.text()
    assert window.info_text.isHidden()
    assert window.metadata_text.isHidden()
    assert "Post ID:" not in window.info_text.toPlainText()
    assert "등급:" not in window.info_text.toPlainText()

    window.close()


def test_decision_shortcuts_apply_even_with_child_focus(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (16, 8), color="blue").save(tmp_path / "b.png")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.caption_text.setFocus()

    window.decision_shortcuts["move"].activated.emit()

    assert app is not None
    assert window.review_decisions[str(tmp_path / "a.png")] == "move"
    assert window.current_record is not None
    assert window.current_record.image_path == tmp_path / "b.png"

    window.close()


def test_floating_preview_metadata_layout_is_stable(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a_long_filename_for_wrap.png")
    Image.new("RGB", (128, 64), color="blue").save(tmp_path / "b.png")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.show()
    window.table.selectRow(0)
    window.show_floating_preview()
    app.processEvents()

    preview = window.floating_preview

    assert app is not None
    assert preview is not None
    assert preview.thumbnail_list.count() == 2
    assert preview.thumbnail_list.currentRow() == 0
    assert preview.thumbnail_list.item(0).text() == "a_long_filename_for_wrap.png"
    assert not preview.thumbnail_list.item(0).icon().isNull()
    assert preview.filename_label.text() == "a_long_filename_for_wrap.png"
    assert preview.resolution_value.text() == "16x8"
    assert preview.file_size_value.text().endswith("B")
    assert preview.file_type_value.text() == "PNG"
    assert preview.decision_value.text() == "미결정"
    assert "A 이동 결정" in preview.guide_label.text()

    value_x = preview.resolution_value.mapTo(preview, QtCore.QPoint(0, 0)).x()
    assert preview.file_size_value.mapTo(preview, QtCore.QPoint(0, 0)).x() == value_x
    assert preview.file_type_value.mapTo(preview, QtCore.QPoint(0, 0)).x() == value_x
    assert preview.decision_value.mapTo(preview, QtCore.QPoint(0, 0)).x() == value_x

    window.select_relative_record(1)
    app.processEvents()

    assert preview.filename_label.text() == "b.png"
    assert preview.thumbnail_list.currentRow() == 1
    assert preview.resolution_value.text() == "128x64"
    assert preview.resolution_value.mapTo(preview, QtCore.QPoint(0, 0)).x() == value_x
    assert preview.file_size_value.mapTo(preview, QtCore.QPoint(0, 0)).x() == value_x

    preview.thumbnail_list.setCurrentRow(0)
    app.processEvents()

    assert window.current_record is not None
    assert window.current_record.image_path.name == "a_long_filename_for_wrap.png"

    window.close()


def test_floating_preview_loads_thumbnails_lazily(tmp_path, monkeypatch):
    for index in range(40):
        Image.new("RGB", (16 + index, 8), color="red").save(tmp_path / f"{index:03d}.png")

    loaded = []

    def fake_thumbnail(path):
        loaded.append(path)
        return QtGui.QPixmap()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(
        main_window_module.FloatingPreviewWindow,
        "make_thumbnail",
        staticmethod(fake_thumbnail),
    )
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.show_floating_preview()
    app.processEvents()

    preview = window.floating_preview

    assert app is not None
    assert preview is not None
    assert preview.thumbnail_list.count() == 40
    assert len(loaded) == preview.THUMBNAIL_PRELOAD_RADIUS + 1

    loaded.clear()
    preview.thumbnail_list.setCurrentRow(30)
    app.processEvents()

    assert 0 < len(loaded) <= (preview.THUMBNAIL_PRELOAD_RADIUS * 2) + 1

    window.close()


def test_duplicate_groups_are_loaded_from_cache(tmp_path, monkeypatch):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (16, 8), color="blue").save(tmp_path / "b.png")
    (tmp_path / "a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": 10}', encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    output_dir = tmp_path / "out"
    window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    window.analyze_duplicate_groups()
    window.close()

    def fail_analyze(*args, **kwargs):
        raise AssertionError("cache was not used")

    monkeypatch.setattr(main_window_module, "analyze_duplicates", fail_analyze)
    cached_window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    cached_window.analyze_duplicate_groups()

    assert app is not None
    assert cached_window.group_table.rowCount() == 1
    assert "캐시된 중복 그룹" in cached_window.status_label.text()

    cached_window.close()


def test_prepare_cache_button_creates_hash_cache(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.prepare_duplicate_cache()

    assert app is not None
    assert ensure_app_data_dirs().hash_cache_path.exists()
    assert "캐시 준비 완료" in window.duplicate_summary_label.text()

    window.close()


def test_floating_preview_drag_handles_adjust_crop_rect(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (100, 80), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.show_floating_preview()
    preview = window.floating_preview

    assert app is not None
    assert preview is not None
    preview.show()
    app.processEvents()

    image_x, image_y, image_width, image_height = preview.preview.image_display_rect()
    top_left = QtCore.QPoint(image_x, image_y)
    top_left_target = QtCore.QPoint(
        image_x + int(image_width * 0.2),
        image_y + int(image_height * 0.25),
    )

    QtTest.QTest.mousePress(preview.preview, QtCore.Qt.MouseButton.LeftButton, pos=top_left)
    QtTest.QTest.mouseMove(preview.preview, top_left_target)
    QtTest.QTest.mouseRelease(
        preview.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=top_left_target,
    )
    app.processEvents()

    crop_rect = window.crop_rects[str(image_path)]

    assert crop_rect[0] > 0
    assert crop_rect[1] > 0
    assert crop_rect[2] < 100
    assert crop_rect[3] < 80

    right_edge = QtCore.QPoint(image_x + image_width, image_y + image_height // 2)
    right_edge_target = QtCore.QPoint(
        image_x + int(image_width * 0.75),
        image_y + image_height // 2,
    )
    QtTest.QTest.mousePress(preview.preview, QtCore.Qt.MouseButton.LeftButton, pos=right_edge)
    QtTest.QTest.mouseMove(preview.preview, right_edge_target)
    QtTest.QTest.mouseRelease(
        preview.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=right_edge_target,
    )
    app.processEvents()

    crop_rect = window.crop_rects[str(image_path)]

    assert window.crop_right.value() > 0
    assert preview.preview.crop_rect == crop_rect
    assert window.preview_label.crop_rect == crop_rect
    assert window.crop_enabled_checkbox.isChecked()
    assert window.crop_left.value() == crop_rect[0]
    assert window.crop_top.value() == crop_rect[1]
    assert window.crop_right.value() == 100 - crop_rect[0] - crop_rect[2]
    assert window.crop_bottom.value() == 80 - crop_rect[1] - crop_rect[3]

    window.close()


def test_full_size_crop_is_not_saved(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (100, 80), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.crop_enabled_checkbox.setChecked(True)

    assert app is not None
    assert str(image_path) not in window.crop_rects
    assert window.crop_enabled_checkbox.isChecked()

    window.close()


def test_batch_crop_ratios_apply_to_all_records(tmp_path):
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    Image.new("RGB", (100, 80), color="red").save(first)
    Image.new("RGB", (200, 120), color="blue").save(second)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.batch_crop_left.setValue(10.0)
    window.batch_crop_top.setValue(25.0)
    window.batch_crop_right.setValue(5.0)
    window.batch_crop_bottom.setValue(10.0)
    window.batch_crop_button.click()

    assert app is not None
    assert window.crop_rects[str(first)] == (10, 20, 85, 52)
    assert window.crop_rects[str(second)] == (20, 30, 170, 78)
    assert window.crop_enabled_checkbox.isChecked()
    assert window.crop_left.value() == 10
    assert window.crop_top.value() == 20

    window.close()


def test_batch_crop_zero_ratios_clear_existing_crops(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (100, 80), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.set_current_crop_rect((10, 10, 80, 60))
    window.batch_crop_button.click()

    assert app is not None
    assert str(image_path) not in window.crop_rects
    assert not window.crop_enabled_checkbox.isChecked()

    window.close()


def test_dragging_crop_to_full_size_clears_crop(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (100, 80), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.set_current_crop_rect((4, 4, 92, 72))
    window.show_floating_preview()
    preview = window.floating_preview
    assert preview is not None
    app.processEvents()

    image_x, image_y, image_width, image_height = preview.preview.image_display_rect()
    display_rect = preview.preview.display_crop_rect()
    assert display_rect is not None
    rect_x, rect_y, _, _ = display_rect
    QtTest.QTest.mousePress(
        preview.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(rect_x, rect_y),
    )
    QtTest.QTest.mouseMove(preview.preview, QtCore.QPoint(image_x, image_y))
    QtTest.QTest.mouseRelease(
        preview.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(image_x, image_y),
    )
    app.processEvents()

    display_rect = preview.preview.display_crop_rect()
    assert display_rect is not None
    rect_x, rect_y, rect_width, rect_height = display_rect
    QtTest.QTest.mousePress(
        preview.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(rect_x + rect_width, rect_y + rect_height),
    )
    QtTest.QTest.mouseMove(
        preview.preview,
        QtCore.QPoint(image_x + image_width - 1, image_y + image_height - 1),
    )
    QtTest.QTest.mouseRelease(
        preview.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(image_x + image_width - 1, image_y + image_height - 1),
    )
    app.processEvents()

    assert str(image_path) not in window.crop_rects
    assert not window.crop_enabled_checkbox.isChecked()

    window.close()


def test_floating_preview_always_on_top_toggle(tmp_path):
    image_path = tmp_path / "a.png"
    Image.new("RGB", (100, 80), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.show_floating_preview()
    preview = window.floating_preview

    assert app is not None
    assert preview is not None
    assert preview.always_on_top_checkbox.isChecked()
    assert bool(preview.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint)

    preview.always_on_top_checkbox.setChecked(False)
    app.processEvents()

    assert not bool(preview.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint)

    window.close()


def test_execute_review_decisions_moves_deleted_files_to_trash(tmp_path, monkeypatch):
    monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / "data"))
    image_path = tmp_path / "a.png"
    caption_path = tmp_path / "a.txt"
    Image.new("RGB", (16, 8), color="red").save(image_path)
    caption_path.write_text("caption", encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    output_dir = tmp_path / "out"
    window = MainWindow(input_dir=tmp_path, output_dir=output_dir, background_tasks=False)
    window.set_current_decision("delete")
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *args, **kwargs: None)

    window.execute_review_decisions()

    assert app is not None
    assert not image_path.exists()
    assert not caption_path.exists()
    paths = ensure_app_data_dirs()
    assert list(paths.trash_dir.rglob("a.png"))
    assert list(paths.trash_dir.rglob("a.txt"))

    window.restore_trash_items()

    assert image_path.exists()
    assert caption_path.read_text(encoding="utf-8") == "caption"

    window.close()


def test_progress_bar_stays_visible_on_duplicate_tab(tmp_path):
    Image.new("RGB", (16, 8)).save(tmp_path / "sample.png")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.show()
    window.tabs.setCurrentIndex(1)

    assert app is not None
    assert window.progress_bar.isVisible()
    assert window.status_label.isVisible()
    assert window.review_splitter.sizes()[0] > window.review_splitter.sizes()[1]
    assert window.duplicate_splitter.sizes()[1] > window.duplicate_splitter.sizes()[0]
    assert len([size for size in window.review_detail_splitter.sizes() if size > 0]) >= 3
    assert window.duplicate_vertical_splitter.sizes()[0] > 0
    assert window.duplicate_vertical_splitter.sizes()[1] > 0
    assert (
        window.table.horizontalHeader().sectionResizeMode(0)
        == QtWidgets.QHeaderView.ResizeMode.Interactive
    )

    window.close()


def test_preview_widget_does_not_overlap_file_info(tmp_path):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (800, 1200), color="red").save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.resize(1100, 720)
    window.show()
    app.processEvents()

    preview_bottom = window.preview_label.mapTo(
        window,
        QtCore.QPoint(0, window.preview_label.height()),
    ).y()
    preview_top = window.preview_label.mapTo(window, QtCore.QPoint(0, 0)).y()
    detail_top = window.review_detail_splitter.mapTo(window, QtCore.QPoint(0, 0)).y()
    info_top = window.info_text.mapTo(window, QtCore.QPoint(0, 0)).y()

    assert preview_top > detail_top
    assert preview_bottom <= info_top
    assert window.preview_label.height() <= window.preview_label.maximumHeight()

    window.close()


def test_background_duplicate_analysis_completes_for_no_candidate_dataset(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (17, 8), color="blue").save(tmp_path / "b.png")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(output_dir=tmp_path / "out", background_tasks=True)
    window.finish_scan(scan_dataset(tmp_path))
    window.use_perceptual_checkbox.setChecked(False)
    window.analyze_duplicate_groups()

    deadline = time.monotonic() + 5
    while window.active_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert window.active_thread is None
    assert window.group_table.rowCount() == 0
    assert window.status_label.text() == "완료"

    window.close()
