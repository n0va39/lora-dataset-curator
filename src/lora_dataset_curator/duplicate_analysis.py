from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from .cache import HashCache
from .grouping import build_duplicate_groups
from .hashing import compute_perceptual_hashes, compute_sha256
from .models import DuplicateGroup, ImageRecord, SimilarityPair
from .similarity import build_hash_pair, is_duplicate_candidate, pair_key

ProgressCallback = Callable[[int, int, str], None]
DEFAULT_MAX_PERCEPTUAL_PAIRS = 500_000
DEFAULT_MAX_WORKERS = min(8, (os.cpu_count() or 1) + 2)


@dataclass(slots=True)
class DuplicateAnalysisResult:
    records: list[ImageRecord]
    pairs: list[SimilarityPair]
    groups: list[DuplicateGroup]
    group_reasons: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class CachePreparationProgress:
    total: int
    current: int = 0

    def advance(self, progress_callback: ProgressCallback | None, message: str) -> None:
        self.current += 1
        self.emit(progress_callback, message)

    def emit(self, progress_callback: ProgressCallback | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(min(self.current, self.total), self.total, message)

    def complete(self, progress_callback: ProgressCallback | None, message: str) -> None:
        self.current = self.total
        self.emit(progress_callback, message)


def prepare_hash_cache(
    records: list[ImageRecord],
    *,
    hash_cache_root: Path | str,
    include_perceptual: bool = True,
    max_workers: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    total = len(records) + (len(records) if include_perceptual else 0)
    progress = CachePreparationProgress(total=max(total, 1))
    progress.emit(progress_callback, "해시 캐시 준비를 시작했습니다.")
    with HashCache(hash_cache_root) as hash_cache:
        attach_sha256(
            records,
            max_workers=max_workers,
            hash_cache=hash_cache,
            progress=progress,
            progress_callback=progress_callback,
        )
        if include_perceptual:
            compute_perceptual_hash_map(
                records,
                max_workers=max_workers,
                hash_cache=hash_cache,
                progress=progress,
                progress_callback=progress_callback,
            )
    progress.complete(progress_callback, "해시 캐시 준비 완료")


def analyze_duplicates(
    records: list[ImageRecord],
    *,
    use_sha256: bool = True,
    use_metadata: bool = True,
    use_perceptual: bool = False,
    phash_threshold: int = 6,
    dhash_threshold: int = 6,
    max_perceptual_pairs: int = DEFAULT_MAX_PERCEPTUAL_PAIRS,
    max_workers: int | None = None,
    hash_cache_root: Path | str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DuplicateAnalysisResult:
    hash_cache = HashCache(hash_cache_root) if hash_cache_root is not None else None
    try:
        return analyze_duplicates_with_cache(
            records,
            use_sha256=use_sha256,
            use_metadata=use_metadata,
            use_perceptual=use_perceptual,
            phash_threshold=phash_threshold,
            dhash_threshold=dhash_threshold,
            max_perceptual_pairs=max_perceptual_pairs,
            max_workers=max_workers,
            hash_cache=hash_cache,
            progress_callback=progress_callback,
        )
    finally:
        if hash_cache is not None:
            hash_cache.close()


def analyze_duplicates_with_cache(
    records: list[ImageRecord],
    *,
    use_sha256: bool,
    use_metadata: bool,
    use_perceptual: bool,
    phash_threshold: int,
    dhash_threshold: int,
    max_perceptual_pairs: int,
    max_workers: int | None,
    hash_cache: HashCache | None,
    progress_callback: ProgressCallback | None,
) -> DuplicateAnalysisResult:
    pair_map: dict[tuple[str, str], SimilarityPair] = {}
    progress = AnalysisProgress(records, use_sha256=use_sha256, use_perceptual=use_perceptual)
    progress.emit(progress_callback, "중복 분석을 시작했습니다.")

    if use_sha256:
        add_sha256_pairs(
            pair_map,
            records,
            max_workers=max_workers,
            hash_cache=hash_cache,
            progress=progress,
            progress_callback=progress_callback,
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
            max_candidate_pairs=max_perceptual_pairs,
            max_workers=max_workers,
            hash_cache=hash_cache,
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
    group_reasons = build_group_reasons(
        groups,
        pairs,
        phash_threshold=phash_threshold,
        dhash_threshold=dhash_threshold,
    )
    progress.complete(progress_callback, "중복 분석 완료")
    return DuplicateAnalysisResult(
        records=records,
        pairs=pairs,
        groups=groups,
        group_reasons=group_reasons,
    )


@dataclass(slots=True)
class AnalysisProgress:
    records: list[ImageRecord]
    use_sha256: bool
    use_perceptual: bool
    extra_total: int = 0
    current: int = 0

    @property
    def total(self) -> int:
        total = 2
        if self.use_sha256:
            total += sha256_candidate_count(self.records)
        if self.use_perceptual:
            total += len(self.records)
        total += self.extra_total
        return max(total, 1)

    def advance(self, progress_callback: ProgressCallback | None, message: str) -> None:
        self.current += 1
        self.emit(progress_callback, message)

    def emit(self, progress_callback: ProgressCallback | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(min(self.current, self.total), self.total, message)

    def complete(self, progress_callback: ProgressCallback | None, message: str) -> None:
        self.current = self.total
        self.emit(progress_callback, message)


def pair_count(count: int) -> int:
    return count * (count - 1) // 2


def sha256_candidate_count(records: Iterable[ImageRecord]) -> int:
    return sum(len(bucket) for bucket in file_size_buckets(records).values())


def file_size_buckets(records: Iterable[ImageRecord]) -> dict[str, list[ImageRecord]]:
    return bucket_records(records, lambda record: record.file_size)


def add_sha256_pairs(
    pair_map: dict[tuple[str, str], SimilarityPair],
    records: Iterable[ImageRecord],
    *,
    max_workers: int | None = None,
    hash_cache: HashCache | None = None,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    candidates = [
        record
        for bucket in file_size_buckets(records).values()
        for record in bucket
    ]
    attach_sha256(
        candidates,
        max_workers=max_workers,
        hash_cache=hash_cache,
        progress=progress,
        progress_callback=progress_callback,
    )
    add_bucket_pairs(
        pair_map,
        bucket_records(candidates, lambda record: record.sha256),
        sha256_match=True,
    )


def attach_sha256(
    records: Iterable[ImageRecord],
    *,
    max_workers: int | None = None,
    hash_cache: HashCache | None = None,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    pending_records: list[ImageRecord] = []
    for record in records:
        if record.sha256 is None:
            cached = hash_cache.load(record) if hash_cache is not None else None
            if cached is not None and cached.sha256:
                record.sha256 = cached.sha256
                if progress is not None:
                    progress.advance(
                        progress_callback,
                        f"SHA256 캐시 사용: {record.image_path.name}",
                    )
                continue
            pending_records.append(record)
        elif progress is not None:
            progress.advance(progress_callback, f"SHA256 계산 중: {record.image_path.name}")

    if not pending_records:
        return

    worker_count = resolve_max_workers(max_workers)
    if worker_count <= 1 or len(pending_records) == 1:
        for record in pending_records:
            try:
                record.sha256 = compute_sha256(record.image_path)
                if hash_cache is not None:
                    hash_cache.save(record, sha256=record.sha256)
            except (OSError, RuntimeError, ValueError):
                record.sha256 = None
            finally:
                if progress is not None:
                    progress.advance(
                        progress_callback,
                        f"SHA256 계산 중: {record.image_path.name}",
                    )
        return

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(compute_sha256, record.image_path): record
            for record in pending_records
        }
        for future in as_completed(futures):
            record = futures[future]
            try:
                record.sha256 = future.result()
                if hash_cache is not None:
                    hash_cache.save(record, sha256=record.sha256)
            except (OSError, RuntimeError, ValueError):
                record.sha256 = None
            finally:
                if progress is not None:
                    progress.advance(
                        progress_callback,
                        f"SHA256 계산 중: {record.image_path.name}",
                    )


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
    max_candidate_pairs: int,
    max_workers: int | None = None,
    hash_cache: HashCache | None = None,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    hashes = compute_perceptual_hash_map(
        records,
        max_workers=max_workers,
        hash_cache=hash_cache,
        progress=progress,
        progress_callback=progress_callback,
    )

    candidate_pairs = build_perceptual_candidate_pairs(
        records,
        hashes,
        threshold=max(phash_threshold, dhash_threshold),
    )
    if len(candidate_pairs) > max_candidate_pairs:
        raise ValueError(
            "pHash/dHash candidate search produced "
            f"{len(candidate_pairs):,} image pairs. "
            "Use a smaller dataset, lower thresholds, or raise "
            f"the pair limit above {max_candidate_pairs:,}."
        )
    if progress is not None:
        progress.extra_total += len(candidate_pairs)
        progress.emit(progress_callback, "pHash/dHash 후보를 비교하는 중입니다.")

    total_pairs = len(candidate_pairs)
    last_progress_index = 0
    for index, (record_a, record_b) in enumerate(candidate_pairs, start=1):
        hashes_a = hashes.get(record_a.image_path)
        hashes_b = hashes.get(record_b.image_path)
        if hashes_a is not None and hashes_b is not None:
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
        if progress is not None and should_emit_pair_progress(index, total_pairs):
            progress.current += index - last_progress_index
            last_progress_index = index
            progress.emit(
                progress_callback,
                f"pHash/dHash 후보 비교 중: {record_a.image_path.name}",
            )


def compute_perceptual_hash_map(
    records: list[ImageRecord],
    *,
    max_workers: int | None = None,
    hash_cache: HashCache | None = None,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[Path, dict[str, str]]:
    if hash_cache is not None:
        attach_sha256(
            records,
            max_workers=max_workers,
            hash_cache=hash_cache,
            progress=None,
            progress_callback=None,
        )
    cached_hashes, pending_records = load_cached_perceptual_hashes(
        records,
        hash_cache=hash_cache,
        progress=progress,
        progress_callback=progress_callback,
    )
    if not pending_records:
        return cached_hashes

    worker_count = resolve_max_workers(max_workers)
    if worker_count <= 1 or len(pending_records) <= 1:
        cached_hashes.update(
            compute_perceptual_hash_map_serial(
                pending_records,
                hash_cache=hash_cache,
                progress=progress,
                progress_callback=progress_callback,
            )
        )
        return cached_hashes

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(compute_perceptual_hashes, record.image_path): record
            for record in pending_records
        }
        for future in as_completed(futures):
            record = futures[future]
            try:
                record_hashes = future.result()
                cached_hashes[record.image_path] = record_hashes
                if hash_cache is not None:
                    hash_cache.save(
                        record,
                        phash=record_hashes.get("phash"),
                        dhash=record_hashes.get("dhash"),
                    )
            except Exception:
                pass
            finally:
                if progress is not None:
                    progress.advance(
                        progress_callback,
                        f"pHash/dHash 계산 중: {record.image_path.name}",
                    )
    return cached_hashes


def load_cached_perceptual_hashes(
    records: list[ImageRecord],
    *,
    hash_cache: HashCache | None = None,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[dict[Path, dict[str, str]], list[ImageRecord]]:
    hashes: dict[Path, dict[str, str]] = {}
    pending_records: list[ImageRecord] = []
    for record in records:
        cached = hash_cache.load(record) if hash_cache is not None else None
        if (
            cached is not None
            and cached.sha256
            and (not cached.phash or not cached.dhash)
        ):
            content_cached = hash_cache.load_by_sha256(cached.sha256)
            if content_cached is not None:
                cached.phash = content_cached.phash or cached.phash
                cached.dhash = content_cached.dhash or cached.dhash
        if cached is not None and cached.phash and cached.dhash:
            hashes[record.image_path] = {"phash": cached.phash, "dhash": cached.dhash}
            if progress is not None:
                progress.advance(
                    progress_callback,
                    f"pHash/dHash 캐시 사용: {record.image_path.name}",
                )
            continue
        pending_records.append(record)
    return hashes, pending_records


def compute_perceptual_hash_map_serial(
    records: list[ImageRecord],
    *,
    hash_cache: HashCache | None = None,
    progress: AnalysisProgress | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[Path, dict[str, str]]:
    hashes: dict[Path, dict[str, str]] = {}
    for record in records:
        try:
            record_hashes = compute_perceptual_hashes(record.image_path)
            hashes[record.image_path] = record_hashes
            if hash_cache is not None:
                hash_cache.save(
                    record,
                    phash=record_hashes.get("phash"),
                    dhash=record_hashes.get("dhash"),
                )
        except Exception:
            continue
        finally:
            if progress is not None:
                progress.advance(
                    progress_callback,
                    f"pHash/dHash 계산 중: {record.image_path.name}",
                )
    return hashes


def resolve_max_workers(max_workers: int | None) -> int:
    if max_workers is None:
        return DEFAULT_MAX_WORKERS
    return max(max_workers, 1)


def build_perceptual_candidate_pairs(
    records: list[ImageRecord],
    hashes: dict[Path, dict[str, str]],
    *,
    threshold: int,
) -> list[tuple[ImageRecord, ImageRecord]]:
    segment_count = segment_count_for_threshold(threshold)
    buckets: dict[tuple[str, int, str], list[ImageRecord]] = defaultdict(list)
    for record in records:
        record_hashes = hashes.get(record.image_path)
        if record_hashes is None:
            continue
        for hash_name in ("phash", "dhash"):
            hash_value = record_hashes.get(hash_name)
            if not hash_value:
                continue
            for index, segment in enumerate(split_hash_segments(hash_value, segment_count)):
                buckets[(hash_name, index, segment)].append(record)

    candidate_keys: set[tuple[str, str]] = set()
    record_by_path = {record.image_path: record for record in records}
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for record_a, record_b in combinations(bucket, 2):
            candidate_keys.add(pair_key(record_a.image_path, record_b.image_path))

    return [
        (record_by_path[Path(left)], record_by_path[Path(right)])
        for left, right in sorted(candidate_keys)
    ]


def segment_count_for_threshold(threshold: int) -> int:
    if threshold <= 7:
        return 8
    if threshold <= 15:
        return 16
    raise ValueError("pHash/dHash bucket search supports thresholds up to 15")


def split_hash_segments(hash_value: str, segment_count: int) -> list[str]:
    segment_length = max(len(hash_value) // segment_count, 1)
    return [
        hash_value[index : index + segment_length]
        for index in range(0, len(hash_value), segment_length)
    ][:segment_count]


def should_emit_pair_progress(index: int, total: int) -> bool:
    return index == 1 or index == total or index % 1000 == 0


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
    *,
    phash_threshold: int = 6,
    dhash_threshold: int = 6,
) -> dict[str, list[str]]:
    group_by_path: dict[Path, str] = {}
    reasons: dict[str, set[str]] = {}
    for group in groups:
        reasons[group.group_id] = set()
        for record in group.images:
            group_by_path[record.image_path] = group.group_id

    for pair in pairs:
        group_id = group_by_path.get(pair.image_a)
        if group_id is None or group_id != group_by_path.get(pair.image_b):
            continue
        if not is_duplicate_candidate(
            pair,
            phash_threshold=phash_threshold,
            dhash_threshold=dhash_threshold,
        ):
            continue
        reasons[group_id].update(pair_reasons(pair))

    return {group_id: sorted(group_reasons) for group_id, group_reasons in reasons.items()}


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
