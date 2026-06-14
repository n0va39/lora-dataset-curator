from __future__ import annotations

import json

from lora_dataset_curator.storage import (
    dataset_state_dir,
    duplicate_groups_file_path,
    ensure_app_data_dirs,
    load_default_profile,
    load_settings,
    save_settings,
    stable_path_key,
)


def test_app_storage_layout_is_created(tmp_path):
    paths = ensure_app_data_dirs()

    assert paths.root == tmp_path / "app_home"
    assert paths.config_dir.is_dir()
    assert paths.profiles_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.dataset_cache_dir.is_dir()
    assert paths.state_dir.is_dir()
    assert paths.decisions_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.settings_path.exists()
    assert paths.default_profile_path.exists()

    settings = json.loads(paths.settings_path.read_text(encoding="utf-8"))
    profile = json.loads(paths.default_profile_path.read_text(encoding="utf-8"))
    assert settings["active_profile"] == "default"
    assert profile["duplicates"]["use_perceptual"] is True
    assert profile["duplicates"]["phash_threshold"] == 6


def test_dataset_cache_uses_stable_path_key(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    state_dir = dataset_state_dir(dataset)

    assert state_dir.name == stable_path_key(dataset)
    assert duplicate_groups_file_path(dataset) == state_dir / "duplicate_groups.json"


def test_old_default_profile_enables_perceptual_by_default(tmp_path):
    paths = ensure_app_data_dirs()
    paths.default_profile_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "default",
                "duplicates": {
                    "use_perceptual": False,
                    "phash_threshold": 6,
                    "dhash_threshold": 6,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    profile = load_default_profile()

    assert profile["duplicates"]["use_perceptual"] is True


def test_settings_are_saved_with_defaults(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    save_settings(
        {
            "last_input_dir": str(input_dir),
            "last_output_dir": str(output_dir),
        }
    )

    settings = load_settings()

    assert settings["active_profile"] == "default"
    assert settings["last_input_dir"] == str(input_dir)
    assert settings["last_output_dir"] == str(output_dir)
