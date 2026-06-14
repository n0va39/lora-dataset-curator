from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .hashing import hash_distance
from .models import ImageRecord, SimilarityPair


def tag_similarity(tags_a: Iterable[str], tags_b: Iterable[str]) -> float:
    set_a = set(tags_a)
    set_b = set(tags_b)
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def combined_tag_similarity(record_a: ImageRecord, record_b: ImageRecord) -> float:
    weighted_scores = [
        (tag_similarity(record_a.tags_artist, record_b.tags_artist), 0.30),
        (tag_similarity(record_a.tags_character, record_b.tags_character), 0.25),
        (tag_similarity(record_a.tags_copyright, record_b.tags_copyright), 0.15),
        (tag_similarity(record_a.tags_general, record_b.tags_general), 0.20),
        (tag_similarity(record_a.tags_meta, record_b.tags_meta), 0.10),
    ]
    return sum(score * weight for score, weight in weighted_scores)


def build_hash_pair(
    record_a: ImageRecord,
    record_b: ImageRecord,
    *,
    phash_a: str | None = None,
    phash_b: str | None = None,
    dhash_a: str | None = None,
    dhash_b: str | None = None,
) -> SimilarityPair:
    phash_distance = None
    dhash_distance = None
    if phash_a and phash_b:
        phash_distance = hash_distance(phash_a, phash_b)
    if dhash_a and dhash_b:
        dhash_distance = hash_distance(dhash_a, dhash_b)

    return SimilarityPair(
        image_a=record_a.image_path,
        image_b=record_b.image_path,
        sha256_match=bool(record_a.sha256 and record_a.sha256 == record_b.sha256),
        md5_match=bool(record_a.source_md5 and record_a.source_md5 == record_b.source_md5),
        post_id_match=bool(record_a.post_id and record_a.post_id == record_b.post_id),
        source_url_match=bool(
            record_a.source_url and record_a.source_url == record_b.source_url
        ),
        phash_distance=phash_distance,
        dhash_distance=dhash_distance,
        tag_similarity=combined_tag_similarity(record_a, record_b),
    )


def is_duplicate_candidate(
    pair: SimilarityPair,
    *,
    phash_threshold: int = 6,
    dhash_threshold: int = 6,
) -> bool:
    if pair.sha256_match or pair.md5_match:
        return True
    if pair.post_id_match or pair.source_url_match:
        return True
    if pair.phash_distance is not None and pair.phash_distance <= phash_threshold:
        return True
    if pair.dhash_distance is not None and pair.dhash_distance <= dhash_threshold:
        return True
    return False


def pair_key(path_a: Path, path_b: Path) -> tuple[str, str]:
    left, right = sorted((str(path_a), str(path_b)))
    return left, right
