from __future__ import annotations

import os
import time

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from lora_dataset_curator.scanner import scan_dataset  # noqa: E402
from lora_dataset_curator.storage import (  # noqa: E402
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


def test_execute_review_decisions_moves_linked_files(tmp_path, monkeypatch):
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
    assert (output_dir / "rejected" / "a.png").exists()
    assert (output_dir / "rejected" / "a.txt").exists()

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
