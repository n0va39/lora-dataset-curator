from __future__ import annotations

import shutil

import pytest
from PIL import Image

from lora_dataset_curator import duplicate_analysis
from lora_dataset_curator.duplicate_analysis import analyze_duplicates
from lora_dataset_curator.scanner import scan_dataset


def test_analyze_duplicates_groups_identical_files_by_sha256(tmp_path):
    image_a = tmp_path / "a.png"
    image_b = tmp_path / "b.png"
    Image.new("RGB", (8, 8), color="red").save(image_a)
    shutil.copyfile(image_a, image_b)

    records = scan_dataset(tmp_path)
    result = analyze_duplicates(records)

    assert len(result.groups) == 1
    assert result.group_reasons[result.groups[0].group_id] == ["sha256"]
    assert {record.image_path.name for record in result.groups[0].images} == {"a.png", "b.png"}


def test_analyze_duplicates_groups_same_metadata_post_id(tmp_path):
    Image.new("RGB", (8, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (8, 8), color="blue").save(tmp_path / "b.png")
    (tmp_path / "a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": 10}', encoding="utf-8")

    records = scan_dataset(tmp_path)
    result = analyze_duplicates(records, use_sha256=False)

    assert len(result.groups) == 1
    assert result.group_reasons[result.groups[0].group_id] == ["post-id"]


def test_analyze_duplicates_reports_progress(tmp_path):
    Image.new("RGB", (8, 8), color="red").save(tmp_path / "a.png")
    records = scan_dataset(tmp_path)
    progress: list[tuple[int, int, str]] = []

    result = analyze_duplicates(
        records,
        progress_callback=lambda current, total, message: progress.append(
            (current, total, message)
        ),
    )

    assert result.records == records
    assert progress
    assert progress[-1][1] >= 1


def test_analyze_duplicates_hashes_only_same_size_candidates(tmp_path, monkeypatch):
    image_a = tmp_path / "a.png"
    image_b = tmp_path / "b.png"
    image_c = tmp_path / "c.png"
    Image.new("RGB", (8, 8), color="red").save(image_a)
    shutil.copyfile(image_a, image_b)
    Image.new("RGB", (16, 16), color="blue").save(image_c)

    original_compute_sha256 = duplicate_analysis.compute_sha256
    hashed_paths = []

    def tracking_compute_sha256(path):
        hashed_paths.append(path.name)
        return original_compute_sha256(path)

    monkeypatch.setattr(duplicate_analysis, "compute_sha256", tracking_compute_sha256)

    records = scan_dataset(tmp_path)
    result = analyze_duplicates(records)

    assert len(result.groups) == 1
    assert sorted(hashed_paths) == ["a.png", "b.png"]


def test_analyze_duplicates_limits_large_perceptual_pair_counts(tmp_path):
    for name in ("a.png", "b.png", "c.png"):
        Image.new("RGB", (8, 8), color="red").save(tmp_path / name)

    records = scan_dataset(tmp_path)

    with pytest.raises(ValueError, match="pHash/dHash comparison"):
        analyze_duplicates(
            records,
            use_sha256=False,
            use_metadata=False,
            use_perceptual=True,
            max_perceptual_pairs=1,
        )
