from __future__ import annotations

import shutil

import pytest
from PIL import Image

from lora_dataset_curator import duplicate_analysis
from lora_dataset_curator.duplicate_analysis import analyze_duplicates, prepare_hash_cache
from lora_dataset_curator.scanner import scan_dataset
from lora_dataset_curator.storage import ensure_app_data_dirs


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
    assert progress[-1][0] == progress[-1][1]
    assert progress[-1][2] == "중복 분석 완료"


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


def test_analyze_duplicates_limits_large_perceptual_pair_counts(tmp_path, monkeypatch):
    for name in ("a.png", "b.png", "c.png"):
        Image.new("RGB", (8, 8), color="red").save(tmp_path / name)

    def fake_perceptual_hashes(path):
        return {"phash": "0000000000000000", "dhash": "0000000000000000"}

    monkeypatch.setattr(duplicate_analysis, "compute_perceptual_hashes", fake_perceptual_hashes)
    records = scan_dataset(tmp_path)

    with pytest.raises(ValueError, match="candidate search"):
        analyze_duplicates(
            records,
            use_sha256=False,
            use_metadata=False,
            use_perceptual=True,
            max_perceptual_pairs=1,
        )


def test_analyze_duplicates_groups_perceptual_bucket_candidates(tmp_path, monkeypatch):
    for name in ("a.png", "b.png", "c.png"):
        Image.new("RGB", (8, 8), color="red").save(tmp_path / name)

    hash_by_name = {
        "a.png": {"phash": "0011223344556677", "dhash": "0011223344556677"},
        "b.png": {"phash": "0011223344556676", "dhash": "0011223344556676"},
        "c.png": {"phash": "ffeeddccbbaa9988", "dhash": "ffeeddccbbaa9988"},
    }

    monkeypatch.setattr(
        duplicate_analysis,
        "compute_perceptual_hashes",
        lambda path: hash_by_name[path.name],
    )

    records = scan_dataset(tmp_path)
    result = analyze_duplicates(
        records,
        use_sha256=False,
        use_metadata=False,
        use_perceptual=True,
        phash_threshold=1,
        dhash_threshold=1,
    )

    assert len(result.groups) == 1
    assert {record.image_path.name for record in result.groups[0].images} == {"a.png", "b.png"}


def test_analyze_duplicates_reuses_perceptual_hash_cache(tmp_path, monkeypatch):
    for name in ("a.png", "b.png"):
        Image.new("RGB", (8, 8), color="red").save(tmp_path / name)

    call_count = 0

    def fake_perceptual_hashes(path):
        nonlocal call_count
        call_count += 1
        return {"phash": "0000000000000000", "dhash": "0000000000000000"}

    monkeypatch.setattr(duplicate_analysis, "compute_perceptual_hashes", fake_perceptual_hashes)
    records = scan_dataset(tmp_path)
    result = analyze_duplicates(
        records,
        use_sha256=False,
        use_metadata=False,
        use_perceptual=True,
        hash_cache_root=tmp_path,
    )

    assert len(result.groups) == 1
    assert call_count == 2
    assert ensure_app_data_dirs().hash_cache_path.exists()

    def fail_perceptual_hashes(path):
        raise AssertionError("hash cache was not used")

    monkeypatch.setattr(duplicate_analysis, "compute_perceptual_hashes", fail_perceptual_hashes)
    cached_records = scan_dataset(tmp_path)
    cached_result = analyze_duplicates(
        cached_records,
        use_sha256=False,
        use_metadata=False,
        use_perceptual=True,
        hash_cache_root=tmp_path,
    )

    assert len(cached_result.groups) == 1


def test_perceptual_hash_cache_survives_image_move(tmp_path, monkeypatch):
    for name in ("a.png", "b.png"):
        Image.new("RGB", (8, 8), color="red").save(tmp_path / name)

    monkeypatch.setattr(
        duplicate_analysis,
        "compute_perceptual_hashes",
        lambda path: {"phash": "0000000000000000", "dhash": "0000000000000000"},
    )
    prepare_hash_cache(scan_dataset(tmp_path), hash_cache_root=tmp_path)

    moved_dir = tmp_path / "moved"
    moved_dir.mkdir()
    shutil.move(tmp_path / "b.png", moved_dir / "b.png")

    def fail_perceptual_hashes(path):
        raise AssertionError("content hash cache was not used")

    monkeypatch.setattr(duplicate_analysis, "compute_perceptual_hashes", fail_perceptual_hashes)
    result = analyze_duplicates(
        scan_dataset(tmp_path),
        use_sha256=False,
        use_metadata=False,
        use_perceptual=True,
        hash_cache_root=tmp_path,
    )

    assert len(result.groups) == 1
    assert {record.image_path.name for record in result.groups[0].images} == {"a.png", "b.png"}
