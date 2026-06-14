from __future__ import annotations

from pathlib import Path

from PIL import Image

from lora_dataset_curator import app as cli_app


def create_split_dataset(root: Path) -> None:
    image_dir = root / "images"
    caption_dir = root / "captions"
    metadata_dir = root / "metadata"
    image_dir.mkdir()
    caption_dir.mkdir()
    metadata_dir.mkdir()

    Image.new("RGB", (16, 8)).save(image_dir / "abc.png")
    (caption_dir / "abc.txt").write_text("tag_a tag_b", encoding="utf-8")
    (metadata_dir / "abc.json").write_text('{"id": 1, "md5": "abc"}', encoding="utf-8")


def test_scan_cli_prints_link_summary(tmp_path, capsys):
    create_split_dataset(tmp_path)

    exit_code = cli_app.main(["scan", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Scanned 1 images" in output
    assert "Captions: 1 linked, 0 missing" in output
    assert "Metadata: 1 linked, 0 missing" in output
    assert "- abc.png [16x8, caption, metadata]" in output


def test_scan_cli_prints_missing_sidecar_counts(tmp_path, capsys):
    Image.new("RGB", (4, 4)).save(tmp_path / "missing.jpg")

    exit_code = cli_app.main(["scan", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Scanned 1 images" in output
    assert "Captions: 0 linked, 1 missing" in output
    assert "Metadata: 0 linked, 1 missing" in output
    assert "- missing.jpg [4x4, no-caption, no-metadata]" in output


def test_plan_cli_prints_linked_dry_run_moves(tmp_path, capsys):
    create_split_dataset(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = cli_app.main(["plan", str(tmp_path), "abc", str(output_dir)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Action: quarantine" in output
    assert "Dry run: true" in output
    assert "images\\abc.png" in output or "images/abc.png" in output
    assert "captions\\abc.txt" in output or "captions/abc.txt" in output
    assert "metadata\\abc.json" in output or "metadata/abc.json" in output
    assert "duplicate_quarantine" in output


def test_duplicates_cli_prints_groups(tmp_path, capsys):
    Image.new("RGB", (8, 8), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (8, 8), color="blue").save(tmp_path / "b.png")
    (tmp_path / "a.json").write_text('{"id": 10}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": 10}', encoding="utf-8")

    exit_code = cli_app.main(["duplicates", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Duplicate groups: 1" in output
    assert "post-id" in output


def test_gitignore_excludes_local_sample_folder():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "sample/" in gitignore.splitlines()


def test_parser_includes_gui_command():
    help_text = cli_app.build_parser().format_help()

    assert "gui" in help_text


def test_no_args_defaults_to_gui(monkeypatch):
    called = {}

    def fake_handle_gui(args):
        called["input_dir"] = args.input_dir
        called["output"] = args.output
        return 0

    monkeypatch.setattr(cli_app, "handle_gui", fake_handle_gui)

    assert cli_app.main([]) == 0
    assert called == {"input_dir": None, "output": None}
