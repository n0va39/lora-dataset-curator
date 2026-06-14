from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import ActionPlan, ImageRecord
from .storage import ensure_app_data_dirs

TRASH_MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class TrashOperationResult:
    restored_files: int = 0
    skipped_files: int = 0
    removed_entries: int = 0
    deleted_entries: int = 0


def make_trash_item_dir(record: ImageRecord) -> Path:
    safe_stem = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in (record.stem or record.image_path.stem)
    ).strip("_")
    if not safe_stem:
        safe_stem = "item"
    safe_stem = safe_stem[:64]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return ensure_app_data_dirs().trash_dir / f"{timestamp}_{uuid4().hex[:8]}_{safe_stem}"


def write_trash_manifest(plan: ActionPlan) -> Path | None:
    if plan.action != "delete" or not plan.moves:
        return None
    item_dir = plan.moves[0].target.parent
    item_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = item_dir / TRASH_MANIFEST_NAME
    manifest = {
        "version": 1,
        "deleted_at": datetime.now(UTC).isoformat(),
        "reason": plan.reason,
        "files": [
            {
                "original": str(move.source),
                "trashed": str(move.target),
            }
            for move in plan.moves
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def restore_trash() -> TrashOperationResult:
    restored = 0
    skipped = 0
    removed_entries = 0
    trash_dir = ensure_app_data_dirs().trash_dir
    for item_dir in trash_items(trash_dir):
        manifest = load_manifest(item_dir / TRASH_MANIFEST_NAME)
        files = manifest.get("files", [])
        if not isinstance(files, list):
            skipped += 1
            continue

        has_remaining_files = False
        for entry in files:
            if not isinstance(entry, dict):
                skipped += 1
                has_remaining_files = True
                continue
            original_value = entry.get("original")
            trashed_value = entry.get("trashed")
            if not isinstance(original_value, str) or not isinstance(trashed_value, str):
                skipped += 1
                has_remaining_files = True
                continue
            original = Path(original_value)
            trashed = Path(trashed_value)
            if not trashed.exists():
                continue
            if original.exists():
                skipped += 1
                has_remaining_files = True
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(trashed), str(original))
            restored += 1

        if not has_remaining_files and not any_remaining_payload_files(item_dir):
            shutil.rmtree(item_dir, ignore_errors=True)
            removed_entries += 1

    return TrashOperationResult(
        restored_files=restored,
        skipped_files=skipped,
        removed_entries=removed_entries,
    )


def empty_trash() -> TrashOperationResult:
    deleted_entries = 0
    trash_dir = ensure_app_data_dirs().trash_dir
    for path in trash_dir.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
            deleted_entries += 1
        else:
            path.unlink()
            deleted_entries += 1
    return TrashOperationResult(deleted_entries=deleted_entries)


def trash_items(trash_dir: Path | None = None) -> list[Path]:
    root = trash_dir or ensure_app_data_dirs().trash_dir
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def any_remaining_payload_files(item_dir: Path) -> bool:
    return any(path.is_file() and path.name != TRASH_MANIFEST_NAME for path in item_dir.rglob("*"))
