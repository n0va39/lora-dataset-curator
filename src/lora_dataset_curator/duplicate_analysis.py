from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from .grouping import build_duplicate_groups
from .hashing import compute_perceptual_hashes, compute_sha256
from .models import DuplicateGroup, ImageRecord, SimilarityPair
from .similarity import build_hash_pair, pair_key

ProgressCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class DuplicateAnalysisResult:
    records: list[ImageRecord]
    pairs: list[SimilarityPair]
    groups: list[DuplicateGroup]
    group_reasons: dict[str, list[str]] = field(default_factory=dict)


def analyze_duplicates(
    records: list[ImageRecord],
    *,
    use_sha256: bool = True,
    use_metadata: bool = True,
    use_perceptual: bool = False,
    phash_threshold: int = 6,
    dhash_threshold: int = 6,
    progress_callback: ProgressCallback | None = None,
) -> DuplicateAnalysisResult:
    pair_map: dict[tuple[str, str], SimilarityPair] = {}
    progress = AnalysisProgress(records, use_sha256=use_sha256, use_perceptual=use_perceptual)
    progress.emit(progress_callback, "중복 분석을 시작했습니다.")

    if use_sha256:
        attach_sha256(records, progress=progress, progress_callback=progress_callback)
        add_bucket_pairs(
            pair_map,
            bucket_records(records, lambda record: record.sha256),
            sha256_match=True,
        )

    if use_metadata:
        progress.emit(progress_callback, "metadata 기준 후보를 묶는 중입니다.")
        add_bucket_pairs(
            pair_map,
            bucket_records(records, lambda record: record.source_md5),
            md5_match=True,
        )
        add_bucket_pairs(
            pair_map,
            bucket_records(records, lambda record: record.post_id),
            post_id_match=True,
        )
        add_bucket_pairs(
            pair_map,
            bucket_records(records, lambda record: record.source_url),
            source_url_match=True,
        )

    if use_perceptual:
        add_perceptual_pairs(
            pair_map,
            records,
            phash_threshold=phash_threshold,
            dhash_threshold=dhash_threshold,
            progress=progress,
            progress_callback=progress_callback,
        )

    progress.emit(progress_callback, "그룹을 생성하는 중입니다.")
    pairs = list(pair_map.values())
    groups = build_duplicate_groups(
        records,
        pairs,
        phash_threshold=phash_threshold,
        dhash_threshold=dhash_threshold,
    )
    return DuplicateAnalysisResult(
        records=records,
        pairs=pairs,
        groups=groups,
        group_reasons=build_group_reasons(groups, pairs),
    )


@dataclass(slots=True)
class AnalysisProgress:
    records: list[ImageRecord]
    use_sha256: bool
    use_perceptual: bool
    current: int = 0

    @property
    def total(self) -> int:
        total = 2
        if self.use_sha256:
            total += len(self.records)
        if self.use_perceptual:
            total += len(self.records) + pair_count(len(self.records))
        return max(total, 1)

    def advance(self, progress_callback: ProgressCallback | None, message: str) -> None:
        self.current += 1
        self.emit(progress_callback, message)

    def emit(self, progress_callback: ProgressCallback | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(min(self.current, self.total), self.total, message)


def pair_count(count: int) -> int:
    return count * (count - 1) // 2


def attach_sha256(
    records: Iterable[ImageRecord],
    *,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    for record in records:
        if record.sha256 is None:
            record.sha256 = compute_sha256(record.image_path)
        if progress is not None:
            progress.advance(progress_callback, f"SHA256 계산 중: {record.image_path.name}")


def bucket_records(
    records: Iterable[ImageRecord],
    key_func,
) -> dict[str, list[ImageRecord]]:
    buckets: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        key = key_func(record)
        if key:
            buckets[str(key)].append(record)
    return {key: bucket for key, bucket in buckets.items() if len(bucket) > 1}


def add_bucket_pairs(
    pair_map: dict[tuple[str, str], SimilarityPair],
    buckets: dict[str, list[ImageRecord]],
    *,
    sha256_match: bool = False,
    md5_match: bool = False,
    post_id_match: bool = False,
    source_url_match: bool = False,
) -> None:
    for records in buckets.values():
        for record_a, record_b in combinations(records, 2):
            pair = get_or_create_pair(pair_map, record_a, record_b)
            pair.sha256_match = pair.sha256_match or sha256_match
            pair.md5_match = pair.md5_match or md5_match
            pair.post_id_match = pair.post_id_match or post_id_match
            pair.source_url_match = pair.source_url_match or source_url_match


def add_perceptual_pairs(
    pair_map: dict[tuple[str, str], SimilarityPair],
    records: list[ImageRecord],
    *,
    phash_threshold: int,
    dhash_threshold: int,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    hashes: dict[Path, dict[str, str]] = {}
    for record in records:
        try:
            hashes[record.image_path] = compute_perceptual_hashes(record.image_path)
        except (OSError, RuntimeError, ValueError):
            continue
        finally:
            if progress is not None:
                progress.advance(
                    progress_callback,
                    f"pHash/dHash 계산 중: {record.image_path.name}",
                )

    for record_a, record_b in combinations(records, 2):
        hashes_a = hashes.get(record_a.image_path)
        hashes_b = hashes.get(record_b.image_path)
        if hashes_a is None or hashes_b is None:
            continue
        pair = build_hash_pair(
            record_a,
            record_b,
            phash_a=hashes_a.get("phash"),
            phash_b=hashes_b.get("phash"),
            dhash_a=hashes_a.get("dhash"),
            dhash_b=hashes_b.get("dhash"),
        )
        if (
            pair.phash_distance is not None
            and pair.phash_distance <= phash_threshold
            or pair.dhash_distance is not None
            and pair.dhash_distance <= dhash_threshold
        ):
            existing = get_or_create_pair(pair_map, record_a, record_b)
            existing.phash_distance = pair.phash_distance
            existing.dhash_distance = pair.dhash_distance
            existing.tag_similarity = pair.tag_similarity
        if progress is not None:
            progress.advance(
                progress_callback,
                f"pHash/dHash 후보 비교 중: {record_a.image_path.name}",
            )


def get_or_create_pair(
    pair_map: dict[tuple[str, str], SimilarityPair],
    record_a: ImageRecord,
    record_b: ImageRecord,
) -> SimilarityPair:
    key = pair_key(record_a.image_path, record_b.image_path)
    pair = pair_map.get(key)
    if pair is None:
        pair = SimilarityPair(image_a=record_a.image_path, image_b=record_b.image_path)
        pair_map[key] = pair
    return pair


def build_group_reasons(
    groups: list[DuplicateGroup],
    pairs: list[SimilarityPair],
) -> dict[str, list[str]]:
    pair_by_key = {pair_key(pair.image_a, pair.image_b): pair for pair in pairs}
    reasons: dict[str, list[str]] = {}
    for group in groups:
        group_reasons: set[str] = set()
        for record_a, record_b in combinations(group.images, 2):
            pair = pair_by_key.get(pair_key(record_a.image_path, record_b.image_path))
            if pair is None:
                continue
            group_reasons.update(pair_reasons(pair))
        reasons[group.group_id] = sorted(group_reasons)
    return reasons


def pair_reasons(pair: SimilarityPair) -> list[str]:
    reasons: list[str] = []
    if pair.sha256_match:
        reasons.append("sha256")
    if pair.md5_match:
        reasons.append("metadata-md5")
    if pair.post_id_match:
        reasons.append("post-id")
    if pair.source_url_match:
        reasons.append("source-url")
    if pair.phash_distance is not None:
        reasons.append(f"phash<={pair.phash_distance}")
    if pair.dhash_distance is not None:
        reasons.append(f"dhash<={pair.dhash_distance}")
    return reasons
