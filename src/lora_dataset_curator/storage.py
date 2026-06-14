from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_DIR_NAME = "lora-dataset-curator"
APP_HOME_ENV = "LORA_DATASET_CURATOR_HOME"
SETTINGS_FILE_NAME = "settings.json"
DEFAULT_PROFILE_NAME = "default"


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    config_dir: Path
    profiles_dir: Path
    cache_dir: Path
    dataset_cache_dir: Path
    state_dir: Path
    decisions_dir: Path
    logs_dir: Path
    settings_path: Path
    default_profile_path: Path
    hash_cache_path: Path


DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "active_profile": DEFAULT_PROFILE_NAME,
    "last_input_dir": None,
    "last_output_dir": None,
}

DEFAULT_PROFILE: dict[str, Any] = {
    "version": 2,
    "name": DEFAULT_PROFILE_NAME,
    "duplicates": {
        "use_perceptual": True,
        "phash_threshold": 6,
        "dhash_threshold": 6,
        "max_perceptual_pairs": 500_000,
    },
    "actions": {
        "delete_mode": "quarantine",
        "move_linked_sidecars": True,
    },
}


def app_data_root() -> Path:
    env_root = os.environ.get(APP_HOME_ENV)
    if env_root:
        return Path(env_root).expanduser().resolve()

    if getattr(sys, "frozen", False):
        portable_root = Path(sys.executable).resolve().parent / "data"
        try:
            portable_root.mkdir(parents=True, exist_ok=True)
            return portable_root
        except OSError:
            pass

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).expanduser().resolve() / APP_DIR_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser().resolve() / APP_DIR_NAME

    return Path.home().expanduser().resolve() / f".{APP_DIR_NAME}"


def app_paths() -> AppPaths:
    root = app_data_root()
    config_dir = root / "config"
    profiles_dir = root / "profiles"
    cache_dir = root / "cache"
    dataset_cache_dir = cache_dir / "datasets"
    state_dir = root / "state"
    decisions_dir = state_dir / "decisions"
    logs_dir = root / "logs"
    return AppPaths(
        root=root,
        config_dir=config_dir,
        profiles_dir=profiles_dir,
        cache_dir=cache_dir,
        dataset_cache_dir=dataset_cache_dir,
        state_dir=state_dir,
        decisions_dir=decisions_dir,
        logs_dir=logs_dir,
        settings_path=config_dir / SETTINGS_FILE_NAME,
        default_profile_path=profiles_dir / f"{DEFAULT_PROFILE_NAME}.json",
        hash_cache_path=cache_dir / "hashes.sqlite",
    )


def ensure_app_data_dirs() -> AppPaths:
    paths = app_paths()
    for directory in (
        paths.config_dir,
        paths.profiles_dir,
        paths.cache_dir,
        paths.dataset_cache_dir,
        paths.state_dir,
        paths.decisions_dir,
        paths.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    write_default_json(paths.settings_path, DEFAULT_SETTINGS)
    write_default_json(paths.default_profile_path, DEFAULT_PROFILE)
    return paths


def write_default_json(path: Path, data: dict[str, Any]) -> None:
    if path.exists():
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_settings() -> dict[str, Any]:
    return DEFAULT_SETTINGS | load_json(ensure_app_data_dirs().settings_path)


def save_settings(settings: dict[str, Any]) -> None:
    paths = ensure_app_data_dirs()
    merged = DEFAULT_SETTINGS | load_json(paths.settings_path) | settings
    paths.settings_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_default_profile() -> dict[str, Any]:
    loaded = load_json(ensure_app_data_dirs().default_profile_path)
    profile = DEFAULT_PROFILE | loaded
    loaded_duplicates = loaded.get("duplicates", {})
    if not isinstance(loaded_duplicates, dict):
        loaded_duplicates = {}
    duplicates = DEFAULT_PROFILE["duplicates"] | loaded_duplicates
    try:
        loaded_version = int(loaded.get("version", 0) or 0)
    except (TypeError, ValueError):
        loaded_version = 0
    if loaded_version < 2:
        duplicates["use_perceptual"] = True
    profile["duplicates"] = duplicates
    return profile


def stable_path_key(path: Path | str) -> str:
    resolved = str(Path(path).expanduser().resolve())
    if os.name == "nt":
        resolved = resolved.casefold()
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


def dataset_state_dir(input_root: Path | str) -> Path:
    paths = ensure_app_data_dirs()
    path = paths.dataset_cache_dir / stable_path_key(input_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def duplicate_groups_file_path(input_root: Path | str) -> Path:
    return dataset_state_dir(input_root) / "duplicate_groups.json"


def decisions_file_path(output_root: Path | str) -> Path:
    paths = ensure_app_data_dirs()
    return paths.decisions_dir / f"{stable_path_key(output_root)}.json"


def hash_cache_file_path() -> Path:
    return ensure_app_data_dirs().hash_cache_path
