from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable
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

ProgressCallback = Callable[[int, int, str], None]


def iter_image_paths(root: Path, *, recursive: bool = True) -> Iterable[Path]:
    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def find_sidecar(stem: str, folder: Path, suffix: str) -> Path | None:
    candidate = folder / f"{stem}{suffix}"
    return candidate if candidate.exists() else None


def find_linked_sidecar(
    image_path: Path,
    image_root: Path,
    sidecar_root: Path,
    suffix: str,
) -> Path | None:
    folders: list[Path] = []
    if sidecar_root == image_root:
        folders.append(image_path.parent)
    else:
        try:
            relative_parent = image_path.parent.relative_to(image_root)
        except ValueError:
            relative_parent = Path()
        folders.extend((sidecar_root / relative_parent, sidecar_root, image_path.parent))

    for folder in dict.fromkeys(folders):
        sidecar = find_sidecar(image_path.stem, folder, suffix)
        if sidecar is not None:
            return sidecar
    return None


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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                return image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return None, None


def build_record(
    image_path: Path,
    image_root: Path,
    caption_root: Path,
    metadata_root: Path,
) -> ImageRecord:
    stem = image_path.stem
    caption_path = find_linked_sidecar(image_path, image_root, caption_root, ".txt")
    metadata_path = find_linked_sidecar(image_path, image_root, metadata_root, ".json")
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


def scan_dataset(
    input_dir: Path | str,
    *,
    recursive: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> list[ImageRecord]:
    root = Path(input_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    image_root, caption_root, metadata_root = resolve_scan_roots(root)
    image_paths = list(iter_image_paths(image_root, recursive=recursive))
    total = len(image_paths)
    if progress_callback is not None:
        progress_callback(0, total, "이미지 파일 목록을 준비했습니다.")

    records: list[ImageRecord] = []
    for index, image_path in enumerate(image_paths, start=1):
        records.append(build_record(image_path, image_root, caption_root, metadata_root))
        if progress_callback is not None:
            progress_callback(index, total, f"스캔 중: {image_path.name}")
    return records
