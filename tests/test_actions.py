from __future__ import annotations

from PIL import Image

from lora_dataset_curator import actions as actions_module
from lora_dataset_curator.actions import build_action_plan, execute_plan
from lora_dataset_curator.models import ImageRecord
from lora_dataset_curator.storage import APP_HOME_ENV, ensure_app_data_dirs
from lora_dataset_curator.trash import empty_trash, restore_trash, trash_items


def test_build_action_plan_moves_linked_files(tmp_path):
    image_path = tmp_path / "1.jpg"
    caption_path = tmp_path / "1.txt"
    metadata_path = tmp_path / "1.json"
    image_path.write_bytes(b"image")
    caption_path.write_text("caption", encoding="utf-8")
    metadata_path.write_text("{}", encoding="utf-8")

    record = ImageRecord(
        image_path=image_path,
        caption_path=caption_path,
        metadata_path=metadata_path,
        stem="1",
        extension=".jpg",
    )

    plan = build_action_plan(record, tmp_path / "output", "quarantine")

    assert plan.dry_run is True
    assert len(plan.moves) == 3
    assert plan.moves[0].target == (
        tmp_path / "output" / "duplicate_quarantine" / "1.jpg"
    ).resolve()


def test_execute_plan_dry_run_does_not_move_files(tmp_path):
    image_path = tmp_path / "1.jpg"
    image_path.write_bytes(b"image")
    record = ImageRecord(image_path=image_path, stem="1", extension=".jpg")
    plan = build_action_plan(record, tmp_path / "output", "keep", dry_run=True)

    moves = execute_plan(plan)

    assert len(moves) == 1
    assert image_path.exists()
    assert not moves[0].target.exists()


def test_execute_plan_crops_moved_image_and_moves_sidecar(tmp_path):
    image_path = tmp_path / "1.png"
    caption_path = tmp_path / "1.txt"
    Image.new("RGB", (10, 8), color="red").save(image_path)
    caption_path.write_text("caption", encoding="utf-8")
    record = ImageRecord(
        image_path=image_path,
        caption_path=caption_path,
        stem="1",
        extension=".png",
    )
    plan = build_action_plan(record, tmp_path / "output", "move", dry_run=False)

    execute_plan(plan, crop_rect=(2, 1, 4, 5))

    target_image = tmp_path / "output" / "1.png"
    target_caption = tmp_path / "output" / "1.txt"
    assert not image_path.exists()
    assert not caption_path.exists()
    assert target_caption.read_text(encoding="utf-8") == "caption"
    with Image.open(target_image) as image:
        assert image.size == (4, 5)


def test_execute_plan_skips_crop_when_rect_is_full_image(tmp_path, monkeypatch):
    image_path = tmp_path / "1.png"
    Image.new("RGB", (10, 8), color="red").save(image_path)
    record = ImageRecord(image_path=image_path, stem="1", extension=".png")
    plan = build_action_plan(record, tmp_path / "output", "move", dry_run=False)

    def fail_crop(*args, **kwargs):
        raise AssertionError("full-image crop should not be executed")

    monkeypatch.setattr(actions_module, "apply_crop_to_image", fail_crop)

    execute_plan(plan, crop_rect=(0, 0, 10, 8))

    target_image = tmp_path / "output" / "1.png"
    assert not image_path.exists()
    with Image.open(target_image) as image:
        assert image.size == (10, 8)


def test_execute_delete_plan_moves_to_app_data_trash_and_restores(tmp_path, monkeypatch):
    monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / "data"))
    image_path = tmp_path / "1.png"
    caption_path = tmp_path / "1.txt"
    Image.new("RGB", (10, 8), color="red").save(image_path)
    caption_path.write_text("caption", encoding="utf-8")
    record = ImageRecord(
        image_path=image_path,
        caption_path=caption_path,
        stem="1",
        extension=".png",
    )

    plan = build_action_plan(record, tmp_path / "output", "delete", dry_run=False)
    paths = ensure_app_data_dirs()

    assert plan.moves[0].target.parent.parent == paths.trash_dir

    execute_plan(plan)

    assert not image_path.exists()
    assert not caption_path.exists()
    assert plan.moves[0].target.exists()
    assert (plan.moves[0].target.parent / "manifest.json").exists()
    assert len(trash_items()) == 1

    result = restore_trash()

    assert result.restored_files == 2
    assert image_path.exists()
    assert caption_path.read_text(encoding="utf-8") == "caption"
    assert trash_items() == []


def test_empty_trash_permanently_removes_trash_items(tmp_path, monkeypatch):
    monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / "data"))
    image_path = tmp_path / "1.png"
    Image.new("RGB", (10, 8), color="red").save(image_path)
    record = ImageRecord(image_path=image_path, stem="1", extension=".png")
    plan = build_action_plan(record, tmp_path / "output", "delete", dry_run=False)

    execute_plan(plan)
    result = empty_trash()

    assert result.deleted_entries == 1
    assert not image_path.exists()
    assert trash_items() == []
