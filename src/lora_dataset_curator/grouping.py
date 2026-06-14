from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import DuplicateGroup, ImageRecord, SimilarityPair
from .similarity import is_duplicate_candidate


def image_tag_count(record: ImageRecord) -> int:
    return sum(
        len(tags)
        for tags in (
            record.tags_artist,
            record.tags_character,
            record.tags_copyright,
            record.tags_general,
            record.tags_meta,
        )
    )


def image_quality_components(record: ImageRecord) -> dict[str, int]:
    return {
        "resolution": record.resolution_pixels,
        "file_size": record.file_size or 0,
        "tags": image_tag_count(record),
        "metadata": sum(
            value is not None for value in (record.post_id, record.source_md5, record.source_url)
        ),
        "caption": len(record.caption_text),
    }


def image_quality_score(record: ImageRecord) -> int:
    components = image_quality_components(record)
    return (
        components["resolution"] // 10_000
        + components["file_size"] // 100_000
        + components["tags"] * 8
        + components["metadata"] * 50
        + min(components["caption"] // 20, 50)
    )


class UnionFind:
    def __init__(self, items: list[Path]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: Path) -> Path:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: Path, right: Path) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def recommend_keep(records: list[ImageRecord]) -> ImageRecord | None:
    if not records:
        return None

    return max(
        records,
        key=lambda record: (
            image_quality_score(record),
            record.resolution_pixels,
            record.file_size or 0,
            image_tag_count(record),
            record.image_path.name,
        ),
    )


def build_duplicate_groups(
    records: list[ImageRecord],
    pairs: list[SimilarityPair],
    *,
    phash_threshold: int = 6,
    dhash_threshold: int = 6,
) -> list[DuplicateGroup]:
    path_to_record = {record.image_path: record for record in records}
    union_find = UnionFind(list(path_to_record))

    for pair in pairs:
        if is_duplicate_candidate(
            pair,
            phash_threshold=phash_threshold,
            dhash_threshold=dhash_threshold,
        ):
            union_find.union(pair.image_a, pair.image_b)

    grouped_paths: dict[Path, list[Path]] = defaultdict(list)
    for path in path_to_record:
        grouped_paths[union_find.find(path)].append(path)

    groups: list[DuplicateGroup] = []
    index = 1
    for paths in grouped_paths.values():
        if len(paths) < 2:
            continue
        group_records = [path_to_record[path] for path in sorted(paths)]
        groups.append(
            DuplicateGroup(
                group_id=f"G{index:04d}",
                images=group_records,
                recommended_keep=recommend_keep(group_records),
            )
        )
        index += 1
    return groups
