from __future__ import annotations

import csv
import shutil
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

from .models import ActionName, ActionPlan, FileMove, ImageRecord


def build_action_plan(
    record: ImageRecord,
    output_root: Path | str,
    action: ActionName,
    *,
    target_bucket: str | None = None,
    dry_run: bool = True,
    reason: str = "",
) -> ActionPlan:
    """Build a safe plan for moving linked image/caption/metadata files.

    `delete` is intentionally mapped to a quarantine-like target. Permanent deletion is not
    performed by this helper.
    """

    output = Path(output_root).expanduser().resolve()
    if target_bucket is None:
        target_bucket = {
            "keep": "keep",
            "move": "selected",
            "quarantine": "duplicate_quarantine",
            "delete": "rejected",
            "skip": "",
        }[action]

    if action == "skip":
        return ActionPlan(action=action, moves=(), dry_run=dry_run, reason=reason)

    target_dir = output / target_bucket
    moves = tuple(
        FileMove(source=path, target=target_dir / path.name) for path in record.linked_paths
    )
    return ActionPlan(action=action, moves=moves, dry_run=dry_run, reason=reason)


def execute_plan(
    plan: ActionPlan,
    *,
    crop_rect: tuple[int, int, int, int] | None = None,
) -> list[FileMove]:
    """Execute a plan unless it is a dry run.

    Returns the list of planned moves. This makes dry-run output easy to inspect in GUI or CLI.
    """

    if plan.dry_run:
        return list(plan.moves)

    moves = list(plan.moves)
    if crop_rect is not None and moves and plan.action in {"keep", "move"}:
        image_move = moves[0]
        apply_crop_to_image(image_move.source, image_move.target, crop_rect)
        image_move.source.unlink()
        moves = moves[1:]

    for move in moves:
        move.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.source), str(move.target))
    return list(plan.moves)


def apply_crop_to_image(
    source: Path,
    target: Path,
    crop_rect: tuple[int, int, int, int],
) -> None:
    x, y, width, height = crop_rect
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid crop size: {crop_rect}")

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        original_format = opened.format
        image = ImageOps.exif_transpose(opened)
        left = max(0, min(x, image.width - 1))
        top = max(0, min(y, image.height - 1))
        right = max(left + 1, min(left + width, image.width))
        bottom = max(top + 1, min(top + height, image.height))
        cropped = image.crop((left, top, right, bottom))
        if original_format:
            cropped.save(target, format=original_format)
        else:
            cropped.save(target)


def append_action_log(log_path: Path | str, record: ImageRecord, plan: ActionPlan) -> None:
    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_file.exists()

    with log_file.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp",
                "image_path",
                "action",
                "target_paths",
                "dry_run",
                "reason",
            ],
        )
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "image_path": str(record.image_path),
                "action": plan.action,
                "target_paths": "|".join(str(move.target) for move in plan.moves),
                "dry_run": str(plan.dry_run).lower(),
                "reason": plan.reason,
            }
        )
