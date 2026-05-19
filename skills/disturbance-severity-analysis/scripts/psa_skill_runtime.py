from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/yuanxuefeng/IEEE39")
FLOW_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
EMT_JOB_NAME = os.environ.get("CLOUDPSS_TEST_EMT_JOB", "电磁暂态仿真方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

for env_path in [ROOT / ".env", *[parent / ".env" for parent in ROOT.parents]]:
    if env_path.exists():
        load_dotenv(env_path)
        break


def configure_local_runtime(skill_id: str) -> Path:
    export_dir = ROOT / "results" / "skill-local-export" / skill_id
    export_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PSA_LOCAL_SAVE_DIR"] = str(export_dir)
    os.environ["SAVETOLOCAL"] = "true"
    os.environ["SAVETOMINIO"] = "false"
    return export_dir


def select_bus_targets(sa: Any, limit: int = 4) -> tuple[list[str], list[str]]:
    bus_keys = list(sa.project.getComponentsByRid("model/CloudPSS/_newBus_3p").keys())[:limit]
    bus_labels = [sa.project.getComponentByKey(key).label for key in bus_keys]
    return bus_keys, bus_labels


def first_existing_path(payload: dict[str, Any], suffixes: tuple[str, ...]) -> str:
    for value in payload.values():
        if isinstance(value, str) and value.lower().endswith(suffixes):
            return value
    raise RuntimeError(f"No path with suffixes {suffixes} found in payload: {payload}")


def path_exists(path_value: str | None) -> bool:
    return bool(path_value and Path(path_value).exists())
