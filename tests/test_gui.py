from __future__ import annotations

import os

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

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
    assert "이미지: 1" in window.summary_label.text()
    assert "캡션: 1개 연결, 0개 누락" in window.summary_label.text()

    window.close()


def test_main_window_populates_duplicate_group_tab(tmp_path):
    Image.new("RGB", (16, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (16, 8), color="blue").save(tmp_path / "b.png")
    (tmp_path / "a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": 10}', encoding="utf-8")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow(input_dir=tmp_path, output_dir=tmp_path / "out", background_tasks=False)
    window.analyze_duplicate_groups()

    assert app is not None
    assert window.group_table.rowCount() == 1
    assert window.group_member_table.rowCount() == 2
    assert "그룹: 1" in window.duplicate_summary_label.text()

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

    window.close()
