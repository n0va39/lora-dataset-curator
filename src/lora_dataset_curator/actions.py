from __future__ import annotations

import csv
import shutil
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

from .models import ActionName, ActionPlan, FileMove, ImageRecord
from .trash import make_trash_item_dir, write_trash_manifest


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

    `delete` is intentionally mapped to the app data trash. Permanent deletion is not
    performed by this helper.
    """

    output = Path(output_root).expanduser().resolve()
    if action == "skip":
        return ActionPlan(action=action, moves=(), dry_run=dry_run, reason=reason)

    if action == "delete" and target_bucket is None:
        target_dir = make_trash_item_dir(record)
    else:
        if target_bucket is None:
            target_bucket = {
                "keep": "keep",
                "move": "",
                "quarantine": "duplicate_quarantine",
                "delete": "rejected",
                "skip": "",
            }[action]
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

    moves = retarget_conflicting_moves(list(plan.moves))
    executed_moves: list[FileMove] = []
    if plan.action == "delete":
        existing_moves = tuple(move for move in moves if move.source.exists())
        write_trash_manifest(
            ActionPlan(
                action=plan.action,
                moves=existing_moves,
                dry_run=plan.dry_run,
                reason=plan.reason,
            )
        )
    if crop_rect is not None and moves and plan.action in {"keep", "move"}:
        image_move = moves[0]
        if (
            image_move.source.exists()
            and not same_path(image_move.source, image_move.target)
            and should_crop_image(image_move.source, crop_rect)
        ):
            apply_crop_to_image(image_move.source, image_move.target, crop_rect)
            image_move.source.unlink()
            executed_moves.append(image_move)
            moves = moves[1:]

    for move in moves:
        if not move.source.exists():
            continue
        if same_path(move.source, move.target):
            continue
        move.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.source), str(move.target))
        executed_moves.append(move)
    return executed_moves


def retarget_conflicting_moves(moves: list[FileMove]) -> list[FileMove]:
    if not needs_conflict_suffix(moves):
        return moves
    for index in range(1, 10_000):
        candidate_moves = [
            FileMove(
                source=move.source,
                target=move.target.with_name(f"{move.target.stem}_{index}{move.target.suffix}"),
            )
            for move in moves
        ]
        if not needs_conflict_suffix(candidate_moves):
            return candidate_moves
    raise FileExistsError("Could not find available target names for file move plan.")


def needs_conflict_suffix(moves: list[FileMove]) -> bool:
    active_moves = [
        move
        for move in moves
        if move.source.exists() and not same_path(move.source, move.target)
    ]
    seen_targets: set[Path] = set()
    for move in active_moves:
        target_key = normalized_path(move.target)
        if target_key in seen_targets:
            return True
        seen_targets.add(target_key)
        if move.target.exists():
            return True
    return False


def same_path(left: Path, right: Path) -> bool:
    return normalized_path(left) == normalized_path(right)


def normalized_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def should_crop_image(source: Path, crop_rect: tuple[int, int, int, int]) -> bool:
    x, y, width, height = crop_rect
    with Image.open(source) as image:
        return not (x <= 0 and y <= 0 and width >= image.width and height >= image.height)


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
