from __future__ import annotations

import argparse
import json
from pathlib import Path

from .actions import build_action_plan
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
    plan_parser.add_argument("--action", choices=["keep", "move", "quarantine", "delete", "skip"], default="quarantine")

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
        print(json.dumps([record_summary(record) for record in records], ensure_ascii=False, indent=2))
        return 0

    print(f"Scanned {len(records)} images")
    for record in records:
        caption = "caption" if record.caption_path else "no-caption"
        metadata = "metadata" if record.metadata_path else "no-metadata"
        size = f"{record.width}x{record.height}" if record.width and record.height else "unknown-size"
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return handle_scan(args)
    if args.command == "plan":
        return handle_plan(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
