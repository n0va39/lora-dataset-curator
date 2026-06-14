from __future__ import annotations

import json

from PIL import Image

from lora_dataset_curator.scanner import scan_dataset


def test_scan_same_folder_links_caption_and_metadata(tmp_path):
    image_path = tmp_path / "123.jpg"
    Image.new("RGB", (64, 32)).save(image_path)
    (tmp_path / "123.txt").write_text("1girl, solo", encoding="utf-8")
    (tmp_path / "123.json").write_text(
        json.dumps(
            {
                "id": 123,
                "md5": "abc",
                "source": "https://example.com/source",
                "rating": "s",
                "tag_string_artist": "artist_a",
                "tag_string_character": "character_a",
            }
        ),
        encoding="utf-8",
    )

    records = scan_dataset(tmp_path)

    assert len(records) == 1
    record = records[0]
    assert record.image_path == image_path.resolve()
    assert record.caption_path == (tmp_path / "123.txt").resolve()
    assert record.metadata_path == (tmp_path / "123.json").resolve()
    assert record.width == 64
    assert record.height == 32
    assert record.caption_text == "1girl, solo"
    assert record.post_id == "123"
    assert record.source_md5 == "abc"
    assert record.tags_artist == ["artist_a"]
    assert record.tags_character == ["character_a"]


def test_scan_split_folder_layout(tmp_path):
    image_dir = tmp_path / "images"
    caption_dir = tmp_path / "captions"
    metadata_dir = tmp_path / "metadata"
    image_dir.mkdir()
    caption_dir.mkdir()
    metadata_dir.mkdir()

    Image.new("RGB", (10, 10)).save(image_dir / "abc.png")
    (caption_dir / "abc.txt").write_text("caption", encoding="utf-8")
    (metadata_dir / "abc.json").write_text("{}", encoding="utf-8")

    records = scan_dataset(tmp_path)

    assert len(records) == 1
    assert records[0].caption_path == (caption_dir / "abc.txt").resolve()
    assert records[0].metadata_path == (metadata_dir / "abc.json").resolve()


def test_scan_nested_same_folder_layout(tmp_path):
    nested_dir = tmp_path / "artist"
    nested_dir.mkdir()

    Image.new("RGB", (12, 12)).save(nested_dir / "nested.webp")
    (nested_dir / "nested.txt").write_text("nested caption", encoding="utf-8")
    (nested_dir / "nested.json").write_text('{"id": 42}', encoding="utf-8")

    records = scan_dataset(tmp_path)

    assert len(records) == 1
    assert records[0].caption_path == (nested_dir / "nested.txt").resolve()
    assert records[0].metadata_path == (nested_dir / "nested.json").resolve()
    assert records[0].caption_text == "nested caption"
    assert records[0].post_id == "42"


def test_scan_nested_split_folder_layout(tmp_path):
    image_dir = tmp_path / "images" / "artist"
    caption_dir = tmp_path / "captions" / "artist"
    metadata_dir = tmp_path / "metadata" / "artist"
    image_dir.mkdir(parents=True)
    caption_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)

    Image.new("RGB", (12, 12)).save(image_dir / "nested.webp")
    (caption_dir / "nested.txt").write_text("nested caption", encoding="utf-8")
    (metadata_dir / "nested.json").write_text('{"id": 42}', encoding="utf-8")

    records = scan_dataset(tmp_path)

    assert len(records) == 1
    assert records[0].caption_path == (caption_dir / "nested.txt").resolve()
    assert records[0].metadata_path == (metadata_dir / "nested.json").resolve()


def test_scan_reports_progress(tmp_path):
    Image.new("RGB", (10, 10)).save(tmp_path / "abc.png")
    progress: list[tuple[int, int, str]] = []

    records = scan_dataset(
        tmp_path,
        progress_callback=lambda current, total, message: progress.append(
            (current, total, message)
        ),
    )

    assert len(records) == 1
    assert progress[0][0:2] == (0, 1)
    assert progress[-1][0:2] == (1, 1)
