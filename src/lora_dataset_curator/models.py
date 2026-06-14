from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
}

ActionName = Literal["keep", "move", "quarantine", "delete", "skip"]


@dataclass(slots=True)
class ImageRecord:
    """One image and its linked LoRA dataset sidecar files."""

    image_path: Path
    caption_path: Path | None = None
    metadata_path: Path | None = None
    stem: str = ""
    extension: str = ""
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    sha256: str | None = None
    file_md5: str | None = None
    source_md5: str | None = None
    post_id: str | None = None
    source_url: str | None = None
    rating: str | None = None
    caption_text: str = ""
    tags_artist: list[str] = field(default_factory=list)
    tags_character: list[str] = field(default_factory=list)
    tags_copyright: list[str] = field(default_factory=list)
    tags_general: list[str] = field(default_factory=list)
    tags_meta: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    review_status: str = "pending"

    @property
    def linked_paths(self) -> list[Path]:
        paths = [self.image_path]
        if self.caption_path is not None:
            paths.append(self.caption_path)
        if self.metadata_path is not None:
            paths.append(self.metadata_path)
        return paths

    @property
    def resolution_pixels(self) -> int:
        if self.width is None or self.height is None:
            return 0
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class FileMove:
    source: Path
    target: Path


@dataclass(frozen=True, slots=True)
class ActionPlan:
    """A safe, inspectable file action plan.

    `dry_run=True` means the caller should show the plan without touching files.
    """

    action: ActionName
    moves: tuple[FileMove, ...] = ()
    dry_run: bool = True
    reason: str = ""


@dataclass(slots=True)
class SimilarityPair:
    image_a: Path
    image_b: Path
    sha256_match: bool = False
    md5_match: bool = False
    post_id_match: bool = False
    source_url_match: bool = False
    phash_distance: int | None = None
    dhash_distance: int | None = None
    ssim_score: float | None = None
    embedding_score: float | None = None
    tag_similarity: float | None = None
    pair_status: str = "pending"


@dataclass(slots=True)
class DuplicateGroup:
    group_id: str
    images: list[ImageRecord]
    recommended_keep: ImageRecord | None = None
    group_status: str = "pending"
