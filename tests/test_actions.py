from __future__ import annotations

from PIL import Image

from lora_dataset_curator.actions import build_action_plan, execute_plan
from lora_dataset_curator.models import ImageRecord


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

    target_image = tmp_path / "output" / "selected" / "1.png"
    target_caption = tmp_path / "output" / "selected" / "1.txt"
    assert not image_path.exists()
    assert not caption_path.exists()
    assert target_caption.read_text(encoding="utf-8") == "caption"
    with Image.open(target_image) as image:
        assert image.size == (4, 5)
