from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .metadata import (
    extract_post_id,
    extract_rating,
    extract_source_md5,
    extract_source_url,
    extract_tag_categories,
    load_metadata,
    read_caption,
)
from .models import IMAGE_EXTENSIONS, ImageRecord


def iter_image_paths(root: Path, *, recursive: bool = True) -> Iterable[Path]:
    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def find_sidecar(stem: str, folder: Path, suffix: str) -> Path | None:
    candidate = folder / f"{stem}{suffix}"
    return candidate if candidate.exists() else None


def resolve_scan_roots(input_dir: Path) -> tuple[Path, Path, Path]:
    """Resolve common dataset layouts.

    If `images/`, `captions/`, or `metadata/` exist, use them. Otherwise use the input root.
    """

    image_root = input_dir / "images" if (input_dir / "images").is_dir() else input_dir
    caption_root = input_dir / "captions" if (input_dir / "captions").is_dir() else input_dir
    metadata_root = input_dir / "metadata" if (input_dir / "metadata").is_dir() else input_dir
    return image_root, caption_root, metadata_root


def read_image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            return image.size
    except (UnidentifiedImageError, OSError):
        return None, None


def build_record(image_path: Path, caption_root: Path, metadata_root: Path) -> ImageRecord:
    stem = image_path.stem
    caption_path = find_sidecar(stem, caption_root, ".txt")
    metadata_path = find_sidecar(stem, metadata_root, ".json")
    width, height = read_image_size(image_path)
    raw_metadata = load_metadata(metadata_path)
    tags = extract_tag_categories(raw_metadata)

    return ImageRecord(
        image_path=image_path,
        caption_path=caption_path,
        metadata_path=metadata_path,
        stem=stem,
        extension=image_path.suffix.lower(),
        width=width,
        height=height,
        file_size=image_path.stat().st_size if image_path.exists() else None,
        source_md5=extract_source_md5(raw_metadata),
        post_id=extract_post_id(raw_metadata),
        source_url=extract_source_url(raw_metadata),
        rating=extract_rating(raw_metadata),
        caption_text=read_caption(caption_path),
        tags_artist=tags["artist"],
        tags_character=tags["character"],
        tags_copyright=tags["copyright"],
        tags_general=tags["general"],
        tags_meta=tags["meta"],
        raw_metadata=raw_metadata,
    )


def scan_dataset(input_dir: Path | str, *, recursive: bool = True) -> list[ImageRecord]:
    root = Path(input_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    image_root, caption_root, metadata_root = resolve_scan_roots(root)
    return [
        build_record(image_path, caption_root, metadata_root)
        for image_path in iter_image_paths(image_root, recursive=recursive)
    ]
