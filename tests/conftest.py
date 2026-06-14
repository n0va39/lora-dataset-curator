from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_app_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LORA_DATASET_CURATOR_HOME", str(tmp_path / "app_home"))
