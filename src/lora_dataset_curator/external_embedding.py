from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from .duplicate_analysis import DuplicateAnalysisResult, ProgressCallback
from .grouping import recommend_keep
from .models import DuplicateGroup, ImageRecord, SimilarityPair
from .storage import dataset_state_dir, ensure_app_data_dirs

DEFAULT_ANIMA_ROOT = Path("D:/ComfyUI/Anima_Lora_work/anima_lora_gui")
DEFAULT_ANIMA_VENV = DEFAULT_ANIMA_ROOT / ".venv"


@dataclass(frozen=True, slots=True)
class AnimaEmbeddingSettings:
    anima_venv: Path
    cell_match_min: float = 0.93
    match_frac_min: float = 0.25
    sim_min: float = 0.5
    grid: int = 7
    ratio: float = 0.8
    min_size: int = 2
    device: str = "cuda"
    batch_size: int = 16
    num_workers: int = 4

    @property
    def anima_root(self) -> Path:
        return self.anima_venv.expanduser().resolve().parent


def detect_anima_venv() -> Path | None:
    env_venv = os.environ.get("ANIMA_LORA_VENV")
    env_root = os.environ.get("ANIMA_LORA_ROOT")
    candidates = [Path(env_venv)] if env_venv else []
    if env_root:
        candidates.append(Path(env_root) / ".venv")
    candidates.append(DEFAULT_ANIMA_VENV)
    for candidate in candidates:
        if is_valid_anima_venv(candidate):
            return candidate
    return None


def is_valid_anima_venv(path: Path | str) -> bool:
    venv = Path(path).expanduser()
    root = venv.parent
    return (
        venv.is_dir()
        and anima_python_path(venv).is_file()
        and anima_grouping_script(root).is_file()
    )


def anima_python_path(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def anima_grouping_script(root: Path) -> Path:
    return root / "scripts" / "curate" / "build_groups.py"


def embedding_groups_path(input_root: Path | str) -> Path:
    return dataset_state_dir(input_root) / "anima_embedding_groups.json"


def run_anima_embedding_grouping(
    records: list[ImageRecord],
    input_root: Path | str,
    settings: AnimaEmbeddingSettings,
    *,
    progress_callback: ProgressCallback | None = None,
) -> DuplicateAnalysisResult:
    input_root = Path(input_root).expanduser().resolve()
    validate_settings(settings)
    out_path = embedding_groups_path(input_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback is not None:
        progress_callback(0, 0, "Anima 임베딩 그룹 분석을 시작했습니다.")

    command = [
        str(anima_python_path(settings.anima_venv)),
        str(anima_grouping_script(settings.anima_root)),
        "--source-dir",
        str(input_root),
        "--out",
        str(out_path),
        "--cell-match-min",
        f"{settings.cell_match_min:g}",
        "--match-frac-min",
        f"{settings.match_frac_min:g}",
        "--sim-min",
        f"{settings.sim_min:g}",
        "--grid",
        str(settings.grid),
        "--ratio",
        f"{settings.ratio:g}",
        "--min-size",
        str(settings.min_size),
        "--device",
        settings.device,
        "--batch-size",
        str(settings.batch_size),
        "--num-workers",
        str(settings.num_workers),
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault(
        "NEAR_TWIN_CACHE",
        str(ensure_app_data_dirs().cache_dir / "anima_near_twin"),
    )

    completed = subprocess.run(
        command,
        cwd=settings.anima_root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        output = "\n".join(
            part.strip()
            for part in (completed.stdout, completed.stderr)
            if part.strip()
        )
        raise RuntimeError(
            "Anima 임베딩 그룹 분석이 실패했습니다.\n"
            f"exit code: {completed.returncode}\n{output}"
        )

    if progress_callback is not None:
        progress_callback(1, 1, "Anima 임베딩 그룹 분석 완료")

    return load_anima_embedding_result(out_path, records, input_root)


def validate_settings(settings: AnimaEmbeddingSettings) -> None:
    if not is_valid_anima_venv(settings.anima_venv):
        raise FileNotFoundError(
            "Anima LoRA venv 경로가 올바르지 않습니다: "
            f"{settings.anima_venv}"
        )
    if settings.grid <= 0:
        raise ValueError("grid must be positive")
    if settings.min_size < 1:
        raise ValueError("min_size must be at least 1")
    if settings.batch_size < 1 or settings.num_workers < 0:
        raise ValueError("batch_size must be positive and num_workers must be non-negative")


def load_anima_embedding_result(
    manifest_path: Path,
    records: list[ImageRecord],
    input_root: Path | str,
) -> DuplicateAnalysisResult:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return anima_manifest_to_result(data, records, input_root)


def anima_manifest_to_result(
    manifest: dict[str, Any],
    records: list[ImageRecord],
    input_root: Path | str,
) -> DuplicateAnalysisResult:
    input_root = Path(input_root).expanduser().resolve()
    record_by_path = {record.image_path.resolve(): record for record in records}
    groups: list[DuplicateGroup] = []
    pairs: list[SimilarityPair] = []
    group_reasons: dict[str, list[str]] = {}

    for index, group_data in enumerate(manifest.get("groups", []), start=1):
        raw_members = group_data.get("members", [])
        if not isinstance(raw_members, list):
            continue
        group_records = []
        for member in raw_members:
            if not isinstance(member, str):
                continue
            record = record_by_path.get((input_root / member).resolve())
            if record is not None:
                group_records.append(record)
        if len(group_records) < 2:
            continue

        group_id = f"E{index:04d}"
        mean_cosine = parse_float(group_data.get("mean_cosine"))
        groups.append(
            DuplicateGroup(
                group_id=group_id,
                images=group_records,
                recommended_keep=recommend_keep(group_records),
            )
        )
        for left, right in combinations(group_records, 2):
            pairs.append(
                SimilarityPair(
                    image_a=left.image_path,
                    image_b=right.image_path,
                    embedding_score=mean_cosine,
                )
            )
        reason = "embedding grid match"
        if mean_cosine is not None:
            reason += f", mean cosine={mean_cosine:.4f}"
        group_reasons[group_id] = [reason]

    return DuplicateAnalysisResult(
        records=records,
        pairs=pairs,
        groups=groups,
        group_reasons=group_reasons,
    )


def parse_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
