from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .actions import build_action_plan
from .duplicate_analysis import (
    DEFAULT_MAX_PERCEPTUAL_PAIRS,
    analyze_duplicates,
    prepare_hash_cache,
)
from .models import DuplicateGroup
from .scanner import scan_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LoRA dataset curator MVP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a dataset directory")
    scan_parser.add_argument("input_dir", type=Path)
    scan_parser.add_argument("--no-recursive", action="store_true")
    scan_parser.add_argument("--json", action="store_true", help="Print scan result as JSON")

    plan_parser = subparsers.add_parser("plan", help="Create a dry-run action plan for one image")
    plan_parser.add_argument("input_dir", type=Path)
    plan_parser.add_argument("image_stem")
    plan_parser.add_argument("output_dir", type=Path)
    plan_parser.add_argument(
        "--action",
        choices=["keep", "move", "quarantine", "delete", "skip"],
        default="quarantine",
    )

    gui_parser = subparsers.add_parser("gui", help="Run the local GUI")
    gui_parser.add_argument("input_dir", nargs="?", type=Path)
    gui_parser.add_argument("--output", type=Path)

    duplicates_parser = subparsers.add_parser(
        "duplicates",
        help="Analyze duplicate and similar image groups",
    )
    duplicates_parser.add_argument("input_dir", type=Path)
    duplicates_parser.add_argument("--perceptual", action="store_true")
    duplicates_parser.add_argument("--phash-threshold", type=int, default=6)
    duplicates_parser.add_argument("--dhash-threshold", type=int, default=6)
    duplicates_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker threads for hash calculation (default: CPU based)",
    )
    duplicates_parser.add_argument(
        "--max-perceptual-pairs",
        type=int,
        default=DEFAULT_MAX_PERCEPTUAL_PAIRS,
        help=(
            "Maximum pair comparisons allowed when --perceptual is enabled "
            f"(default: {DEFAULT_MAX_PERCEPTUAL_PAIRS})"
        ),
    )
    duplicates_parser.add_argument("--json", action="store_true", help="Print groups as JSON")

    cache_parser = subparsers.add_parser(
        "prepare-cache",
        help="Precompute SHA256 and perceptual hashes for a dataset",
    )
    cache_parser.add_argument("input_dir", type=Path)
    cache_parser.add_argument(
        "--no-perceptual",
        action="store_true",
        help="Only prepare SHA256 values",
    )
    cache_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker threads for hash calculation (default: CPU based)",
    )

    return parser


def record_summary(record) -> dict[str, object]:
    return {
        "image_path": str(record.image_path),
        "caption_path": str(record.caption_path) if record.caption_path else None,
        "metadata_path": str(record.metadata_path) if record.metadata_path else None,
        "width": record.width,
        "height": record.height,
        "file_size": record.file_size,
        "post_id": record.post_id,
        "source_md5": record.source_md5,
        "source_url": record.source_url,
        "rating": record.rating,
        "caption_length": len(record.caption_text),
        "artist_tags": record.tags_artist,
        "character_tags": record.tags_character,
        "copyright_tags": record.tags_copyright,
    }


def handle_scan(args: argparse.Namespace) -> int:
    records = scan_dataset(args.input_dir, recursive=not args.no_recursive)
    if args.json:
        print(
            json.dumps(
                [record_summary(record) for record in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    caption_count = sum(record.caption_path is not None for record in records)
    metadata_count = sum(record.metadata_path is not None for record in records)
    image_count = len(records)

    print(f"Scanned {image_count} images")
    print(f"Captions: {caption_count} linked, {image_count - caption_count} missing")
    print(f"Metadata: {metadata_count} linked, {image_count - metadata_count} missing")
    for record in records:
        caption = "caption" if record.caption_path else "no-caption"
        metadata = "metadata" if record.metadata_path else "no-metadata"
        size = (
            f"{record.width}x{record.height}"
            if record.width and record.height
            else "unknown-size"
        )
        print(f"- {record.image_path.name} [{size}, {caption}, {metadata}]")
    return 0


def handle_plan(args: argparse.Namespace) -> int:
    records = scan_dataset(args.input_dir)
    record = next((item for item in records if item.stem == args.image_stem), None)
    if record is None:
        raise SystemExit(f"Image stem not found: {args.image_stem}")

    plan = build_action_plan(record, args.output_dir, args.action, dry_run=True)
    print(f"Action: {plan.action}")
    print("Dry run: true")
    for move in plan.moves:
        print(f"- {move.source} -> {move.target}")
    return 0


def handle_gui(args: argparse.Namespace) -> int:
    try:
        from .ui.main_window import run_gui
    except ImportError as exc:
        raise SystemExit("PySide6 is required. Install with: uv sync --extra gui") from exc

    return run_gui(input_dir=args.input_dir, output_dir=args.output)


def handle_duplicates(args: argparse.Namespace) -> int:
    records = scan_dataset(args.input_dir)
    try:
        result = analyze_duplicates(
            records,
            use_perceptual=args.perceptual,
            phash_threshold=args.phash_threshold,
            dhash_threshold=args.dhash_threshold,
            max_perceptual_pairs=args.max_perceptual_pairs,
            max_workers=args.workers,
            hash_cache_root=args.input_dir,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.json:
        print(
            json.dumps(
                [duplicate_group_summary(group, result.group_reasons) for group in result.groups],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"Scanned {len(records)} images")
    print(f"Candidate pairs: {len(result.pairs)}")
    print(f"Duplicate groups: {len(result.groups)}")
    for group in result.groups:
        reasons = ", ".join(result.group_reasons.get(group.group_id, [])) or "unknown"
        keep = group.recommended_keep.image_path.name if group.recommended_keep else ""
        print(f"- {group.group_id}: {len(group.images)} images [{reasons}] keep={keep}")
        for record in group.images:
            marker = "*" if group.recommended_keep == record else " "
            print(f"  {marker} {record.image_path}")
    return 0


def handle_prepare_cache(args: argparse.Namespace) -> int:
    records = scan_dataset(args.input_dir)
    prepare_hash_cache(
        records,
        hash_cache_root=args.input_dir,
        include_perceptual=not args.no_perceptual,
        max_workers=args.workers,
    )
    print(f"Prepared hash cache for {len(records)} images")
    print(f"Cache: {args.input_dir / '.lora_dataset_curator' / 'hashes.sqlite'}")
    return 0


def duplicate_group_summary(
    group: DuplicateGroup,
    group_reasons: dict[str, list[str]],
) -> dict[str, object]:
    return {
        "group_id": group.group_id,
        "count": len(group.images),
        "reasons": group_reasons.get(group.group_id, []),
        "recommended_keep": str(group.recommended_keep.image_path)
        if group.recommended_keep
        else None,
        "images": [str(record.image_path) for record in group.images],
    }


def normalize_argv(argv: list[str] | None) -> list[str]:
    resolved = list(sys.argv[1:] if argv is None else argv)
    return ["gui"] if not resolved else resolved


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(argv))
    if args.command == "scan":
        return handle_scan(args)
    if args.command == "plan":
        return handle_plan(args)
    if args.command == "gui":
        return handle_gui(args)
    if args.command == "duplicates":
        return handle_duplicates(args)
    if args.command == "prepare-cache":
        return handle_prepare_cache(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
