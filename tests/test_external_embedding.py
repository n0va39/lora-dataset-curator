from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from lora_dataset_curator.external_embedding import (
    AnimaEmbeddingSettings,
    anima_manifest_to_result,
    embedding_groups_path,
    load_cached_anima_embedding_result,
    run_anima_embedding_grouping,
)
from lora_dataset_curator.scanner import scan_dataset


def test_anima_manifest_is_converted_to_duplicate_result(tmp_path):
    artist_dir = tmp_path / "artist"
    artist_dir.mkdir()
    Image.new("RGB", (16, 16), color="red").save(artist_dir / "a.png")
    Image.new("RGB", (16, 16), color="red").save(artist_dir / "b.png")
    Image.new("RGB", (16, 16), color="blue").save(artist_dir / "c.png")
    records = scan_dataset(tmp_path)

    result = anima_manifest_to_result(
        {
            "groups": [
                {
                    "id": 1,
                    "artist": "artist",
                    "mean_cosine": 0.9876,
                    "members": ["artist/a.png", "artist/b.png"],
                }
            ]
        },
        records,
        tmp_path,
    )

    assert len(result.groups) == 1
    assert result.groups[0].group_id == "E0001"
    assert {record.image_path.name for record in result.groups[0].images} == {
        "a.png",
        "b.png",
    }
    assert len(result.pairs) == 1
    assert result.pairs[0].embedding_score == 0.9876
    assert "embedding grid match" in result.group_reasons["E0001"][0]


def test_run_anima_embedding_grouping_invokes_external_script(tmp_path, monkeypatch):
    Image.new("RGB", (16, 16), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (16, 16), color="red").save(tmp_path / "b.png")
    records = scan_dataset(tmp_path)
    anima_root = tmp_path / "anima"
    anima_venv = anima_root / ".venv"
    script = anima_root / "scripts" / "curate" / "build_groups.py"
    python = anima_venv / "Scripts" / "python.exe"
    script.parent.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    python.write_text("", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["cwd"] = kwargs["cwd"]
        seen["env"] = kwargs["env"]
        out_index = command.index("--out") + 1
        out_path = Path(command[out_index])
        out_path.write_text(
            """
            {
              "groups": [
                {"mean_cosine": 1.0, "members": ["a.png", "b.png"]}
              ]
            }
            """,
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("lora_dataset_curator.external_embedding.subprocess.run", fake_run)

    result = run_anima_embedding_grouping(
        records,
        tmp_path,
        AnimaEmbeddingSettings(anima_venv=anima_venv, device="cpu"),
    )

    command = seen["command"]
    assert command[0] == str(python)
    assert command[1] == str(script)
    assert "--source-dir" in command
    assert seen["cwd"] == anima_root
    assert seen["env"]["PYTHONUTF8"] == "1"
    assert embedding_groups_path(tmp_path).exists()
    assert len(result.groups) == 1


def test_load_cached_anima_embedding_result_restores_manifest(tmp_path):
    Image.new("RGB", (16, 16), color="red").save(tmp_path / "a.png")
    Image.new("RGB", (16, 16), color="red").save(tmp_path / "b.png")
    records = scan_dataset(tmp_path)
    embedding_groups_path(tmp_path).write_text(
        """
        {
          "groups": [
            {"mean_cosine": 0.99, "members": ["a.png", "b.png"]}
          ]
        }
        """,
        encoding="utf-8",
    )

    result = load_cached_anima_embedding_result(records, tmp_path)

    assert result is not None
    assert len(result.groups) == 1
    assert result.groups[0].group_id == "E0001"
