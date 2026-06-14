from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DuplicateGroup, ImageRecord, SimilarityPair

CACHE_DIR_NAME = ".lora_dataset_curator"
DECISIONS_FILE_NAME = "decisions.json"
DUPLICATE_GROUPS_FILE_NAME = "duplicate_groups.json"


def cache_dir(output_root: Path | str) -> Path:
    return Path(output_root).expanduser().resolve() / CACHE_DIR_NAME


def decisions_path(output_root: Path | str) -> Path:
    return cache_dir(output_root) / DECISIONS_FILE_NAME


def duplicate_groups_path(output_root: Path | str) -> Path:
    return cache_dir(output_root) / DUPLICATE_GROUPS_FILE_NAME


def load_decisions(output_root: Path | str) -> dict[str, str]:
    path = decisions_path(output_root)
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        return {}
    decisions = data.get("decisions", {})
    if not isinstance(decisions, dict):
        return {}
    return {
        str(image_path): str(action)
        for image_path, action in decisions.items()
        if action in {"move", "delete", "skip"}
    }


def save_decisions(output_root: Path | str, decisions: dict[str, str]) -> None:
    write_json(decisions_path(output_root), {"version": 1, "decisions": decisions})


def save_duplicate_result(
    output_root: Path | str,
    input_root: Path | str,
    records: list[ImageRecord],
    result,
    *,
    use_perceptual: bool,
    phash_threshold: int,
    dhash_threshold: int,
) -> None:
    data = {
        "version": 1,
        "input_root": str(Path(input_root).expanduser().resolve()),
        "settings": {
            "use_perceptual": use_perceptual,
            "phash_threshold": phash_threshold,
            "dhash_threshold": dhash_threshold,
        },
        "fingerprints": {
            str(record.image_path): file_fingerprint(record.image_path)
            for record in records
        },
        "pairs": [serialize_pair(pair) for pair in result.pairs],
        "groups": [
            {
                "group_id": group.group_id,
                "images": [str(record.image_path) for record in group.images],
                "recommended_keep": str(group.recommended_keep.image_path)
                if group.recommended_keep
                else None,
                "reasons": result.group_reasons.get(group.group_id, []),
            }
            for group in result.groups
        ],
    }
    write_json(duplicate_groups_path(output_root), data)


def load_duplicate_result(
    output_root: Path | str,
    input_root: Path | str,
    records: list[ImageRecord],
    *,
    use_perceptual: bool,
    phash_threshold: int,
    dhash_threshold: int,
    result_type,
) -> Any | None:
    path = duplicate_groups_path(output_root)
    if not path.exists():
        return None
    data = read_json(path)
    if data.get("input_root") != str(Path(input_root).expanduser().resolve()):
        return None
    settings = data.get("settings", {})
    if settings != {
        "use_perceptual": use_perceptual,
        "phash_threshold": phash_threshold,
        "dhash_threshold": dhash_threshold,
    }:
        return None
    fingerprints = data.get("fingerprints", {})
    if not isinstance(fingerprints, dict) or not fingerprints_match(records, fingerprints):
        return None

    record_by_path = {str(record.image_path): record for record in records}
    groups = []
    group_reasons: dict[str, list[str]] = {}
    for group_data in data.get("groups", []):
        group_records = [
            record_by_path[path]
            for path in group_data.get("images", [])
            if path in record_by_path
        ]
        if len(group_records) < 2:
            continue
        keep_path = group_data.get("recommended_keep")
        groups.append(
            DuplicateGroup(
                group_id=group_data.get("group_id", ""),
                images=group_records,
                recommended_keep=record_by_path.get(keep_path),
            )
        )
        group_reasons[group_data.get("group_id", "")] = list(group_data.get("reasons", []))

    pairs = [deserialize_pair(pair) for pair in data.get("pairs", [])]
    return result_type(
        records=records,
        pairs=pairs,
        groups=groups,
        group_reasons=group_reasons,
    )


def fingerprints_match(records: list[ImageRecord], fingerprints: dict[str, Any]) -> bool:
    if {str(record.image_path) for record in records} != set(fingerprints):
        return False
    return all(
        fingerprints[str(record.image_path)] == file_fingerprint(record.image_path)
        for record in records
    )


def file_fingerprint(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def serialize_pair(pair: SimilarityPair) -> dict[str, Any]:
    return {
        "image_a": str(pair.image_a),
        "image_b": str(pair.image_b),
        "sha256_match": pair.sha256_match,
        "md5_match": pair.md5_match,
        "post_id_match": pair.post_id_match,
        "source_url_match": pair.source_url_match,
        "phash_distance": pair.phash_distance,
        "dhash_distance": pair.dhash_distance,
        "tag_similarity": pair.tag_similarity,
    }


def deserialize_pair(data: dict[str, Any]) -> SimilarityPair:
    return SimilarityPair(
        image_a=Path(data["image_a"]),
        image_b=Path(data["image_b"]),
        sha256_match=bool(data.get("sha256_match")),
        md5_match=bool(data.get("md5_match")),
        post_id_match=bool(data.get("post_id_match")),
        source_url_match=bool(data.get("source_url_match")),
        phash_distance=data.get("phash_distance"),
        dhash_distance=data.get("dhash_distance"),
        tag_similarity=data.get("tag_similarity"),
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
