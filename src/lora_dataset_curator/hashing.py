from __future__ import annotations

import hashlib
from pathlib import Path


def compute_sha256(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_file_md5(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_perceptual_hashes(path: Path | str) -> dict[str, str]:
    """Compute perceptual hashes when optional imagehash dependency is installed."""

    try:
        import imagehash
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Install the image extra to use perceptual hashing") from exc

    with Image.open(path) as image:
        return {
            "phash": str(imagehash.phash(image)),
            "dhash": str(imagehash.dhash(image)),
            "whash": str(imagehash.whash(image)),
        }


def hash_distance(hash_a: str, hash_b: str) -> int:
    """Return Hamming distance between two hexadecimal hash strings."""

    if len(hash_a) != len(hash_b):
        raise ValueError("Hash strings must have the same length")
    return (int(hash_a, 16) ^ int(hash_b, 16)).bit_count()
