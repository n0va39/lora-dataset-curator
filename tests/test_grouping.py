from __future__ import annotations

from lora_dataset_curator.grouping import build_duplicate_groups, recommend_keep
from lora_dataset_curator.models import ImageRecord, SimilarityPair


def test_recommend_keep_prefers_metadata_and_resolution(tmp_path):
    small = ImageRecord(image_path=tmp_path / "small.jpg", width=100, height=100, file_size=100)
    large = ImageRecord(
        image_path=tmp_path / "large.jpg",
        width=200,
        height=200,
        file_size=200,
        post_id="1",
        source_md5="abc",
    )

    assert recommend_keep([small, large]) == large


def test_build_duplicate_groups_from_sha_match(tmp_path):
    image_a = ImageRecord(image_path=tmp_path / "a.jpg", sha256="same")
    image_b = ImageRecord(image_path=tmp_path / "b.jpg", sha256="same")
    pair = SimilarityPair(image_a=image_a.image_path, image_b=image_b.image_path, sha256_match=True)

    groups = build_duplicate_groups([image_a, image_b], [pair])

    assert len(groups) == 1
    assert groups[0].group_id == "G0001"
    assert {record.image_path.name for record in groups[0].images} == {"a.jpg", "b.jpg"}
