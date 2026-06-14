from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def read_caption(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def load_metadata(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def split_tag_string(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [tag for tag in str(value).split() if tag]


def first_existing(metadata: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def extract_post_id(metadata: Mapping[str, Any]) -> str | None:
    value = first_existing(metadata, ("post_id", "id"))
    return None if value is None else str(value)


def extract_source_md5(metadata: Mapping[str, Any]) -> str | None:
    value = first_existing(metadata, ("md5", "source_md5", "danbooru_md5"))
    return None if value is None else str(value)


def extract_source_url(metadata: Mapping[str, Any]) -> str | None:
    value = first_existing(metadata, ("source", "source_url", "file_url", "large_file_url"))
    return None if value is None else str(value)


def extract_rating(metadata: Mapping[str, Any]) -> str | None:
    value = first_existing(metadata, ("rating",))
    return None if value is None else str(value)


def extract_tag_categories(metadata: Mapping[str, Any]) -> dict[str, list[str]]:
    """Extract Danbooru-style tag categories from flexible metadata keys."""

    return {
        "artist": split_tag_string(
            first_existing(metadata, ("tag_string_artist", "tags_artist", "artist_tags"))
        ),
        "character": split_tag_string(
            first_existing(metadata, ("tag_string_character", "tags_character", "character_tags"))
        ),
        "copyright": split_tag_string(
            first_existing(metadata, ("tag_string_copyright", "tags_copyright", "copyright_tags"))
        ),
        "general": split_tag_string(
            first_existing(metadata, ("tag_string_general", "tags_general", "general_tags"))
        ),
        "meta": split_tag_string(
            first_existing(metadata, ("tag_string_meta", "tags_meta", "meta_tags"))
        ),
    }
