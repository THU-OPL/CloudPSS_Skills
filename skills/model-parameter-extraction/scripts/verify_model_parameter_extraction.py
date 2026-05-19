from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT.parent
for source_path in [ROOT / "src"]:
    if source_path.exists() and str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

os.environ.setdefault("CET_MAX_RETRY_COUNT", "2")
os.environ.setdefault("CET_RETRY_SLEEP_SECONDS", "5")
os.environ.setdefault("CET_STATUS_CHECK_INTERVAL", "2")

repo_env = ROOT / ".env"
if repo_env.exists():
    load_dotenv(repo_env)
elif not os.getenv("SIMSTUDIO_TOKEN") or not os.getenv("CLOUDPSS_API_URL"):
    if os.getenv("CLOUDPSS_IGNORE_PARENT_ENV", "").lower() not in {"1", "true", "yes"}:
        for parent in ROOT.parents:
            env_path = parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                break

from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402


MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/yuanxuefeng/IEEE39")
FLOW_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")
MIN_BUS_COUNT = int(os.environ.get("CLOUDPSS_TEST_MIN_BUS_COUNT", "39"))
EXPORT_FULL = os.environ.get("CLOUDPSS_PARAM_EXPORT_FULL", "").lower() in {"1", "true", "yes"}
EXPORT_DIR = ROOT / "results" / "skill-local-export" / "model-parameter-extraction"
RID_GROUPS = {
    "buses": ["model/CloudPSS/_newBus_3p"],
    "lines": ["model/CloudPSS/TransmissionLine"],
    "transformers": [
        "model/CloudPSS/_newTransformer_3p2w",
        "model/CloudPSS/_newTransformer_3p3w",
    ],
    "generators": [
        "model/CloudPSS/SyncGeneratorRouter",
        "model/CloudPSS/_newACVoltageSource_3p",
        "model/CloudPSS/WGSource",
        "model/CloudPSS/PVStation",
    ],
    "loads": ["model/CloudPSS/_newExpLoad_3p"],
    "channels": ["model/CloudPSS/_newChannel"],
}


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def build_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=MODEL_ID)
    log(f"init-done result={result}")
    return sa


def component_cells(revision: dict[str, Any]) -> list[dict[str, Any]]:
    cells = revision["implements"]["diagram"]["cells"]
    return [
        {
            "id": key,
            "label": value.get("label"),
            "definition": value.get("definition"),
            "shape": value.get("shape"),
            "args": value.get("args", {}),
            "pins": value.get("pins", {}),
        }
        for key, value in cells.items()
        if isinstance(value, dict) and "definition" in value and "shape" in value
    ]


def redact_large_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): redact_large_values(v) for k, v in list(value.items())[:25]}
    if isinstance(value, list):
        return [redact_large_values(item) for item in value[:10]]
    return value


def group_components(cells: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in RID_GROUPS}
    for cell in cells:
        for group_name, rids in RID_GROUPS.items():
            if cell["definition"] in rids:
                grouped[group_name].append(cell)
                break
    return grouped


def summarize_parameter_tables(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for group_name, rows in grouped.items():
        arg_keys = Counter()
        for row in rows:
            arg_keys.update((row.get("args") or {}).keys())
        tables[group_name] = {
            "count": len(rows),
            "common_arg_keys": [key for key, _ in arg_keys.most_common(15)],
            "sample_records": [
                {
                    "id": row["id"],
                    "label": row.get("label"),
                    "definition": row.get("definition"),
                    "args": redact_large_values(row.get("args", {})),
                    "pins": redact_large_values(row.get("pins", {})),
                }
                for row in rows[:3]
            ],
        }
    return tables


def summarize_power_flow_settings(settings: list[list[Any]]) -> dict[str, Any]:
    type_counts = Counter(str(row[1]) for row in settings if len(row) > 1)
    return {
        "setting_count": len(settings),
        "type_counts": dict(sorted(type_counts.items())),
        "sample_settings": settings[:10],
    }


def summarize_power_flow_results(sa: PowerSystemAnalysis) -> dict[str, Any]:
    bus_rows = sa.get_bus_all_pf_result()
    line_rows = sa.get_acline_all_pf_result()
    gen_result = sa.get_generator_all_pf_result()
    voltages = [float(row[2]) for row in bus_rows]
    line_losses = [float(row[3]) + float(row[5]) for row in line_rows]
    gen_p = [float(value) for value in gen_result[2]]
    gen_q = [float(value) for value in gen_result[3]]
    return {
        "bus_count": len(bus_rows),
        "line_count": len(line_rows),
        "generator_count": len(gen_result[0]),
        "voltage_min_pu": min(voltages),
        "voltage_max_pu": max(voltages),
        "voltage_avg_pu": statistics.fmean(voltages),
        "total_active_loss_mw": sum(line_losses),
        "total_gen_p_mw": sum(gen_p),
        "total_gen_q_mvar": sum(gen_q),
        "sample_bus_results": bus_rows[:5],
        "sample_line_results": line_rows[:5],
    }


def maybe_export_full(payload: dict[str, Any]) -> str | None:
    if not EXPORT_FULL:
        return None
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"model_parameters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def main() -> None:
    sa = build_case()
    revision = sa.getRevision()
    cells = component_cells(revision)
    grouped = group_components(cells)
    component_counts = {name: len(rows) for name, rows in grouped.items()}

    settings = sa.get_power_flow_settings()
    generator_p_set = sa.get_generator_all_p_set()
    generator_v_set = sa.get_generator_all_v_set()
    load_p_set = sa.get_load_all_p_set()
    load_q_set = sa.get_load_all_q_set()

    log("power-flow validation start")
    pf_result = sa.power_flow_sample_simple_ramdom(
        flowJobName=FLOW_JOB_NAME,
        flowConfigname=CONFIG_NAME,
        P_low=1.0,
        P_high=1.0,
        V_low=1.0,
        V_high=1.0,
    )
    if pf_result.get("status") != "success":
        raise RuntimeError(f"Power flow validation failed: {pf_result}")
    pf_summary = summarize_power_flow_results(sa)
    log("power-flow validation done")

    if component_counts["buses"] < MIN_BUS_COUNT:
        raise RuntimeError(f"Unexpected bus count: {component_counts['buses']}")
    if component_counts["lines"] == 0:
        raise RuntimeError("No lines discovered")
    if component_counts["generators"] == 0:
        raise RuntimeError("No generators discovered")
    if component_counts["loads"] == 0:
        raise RuntimeError("No loads discovered")
    if pf_summary["bus_count"] < MIN_BUS_COUNT:
        raise RuntimeError(f"Unexpected power-flow bus count: {pf_summary['bus_count']}")

    full_payload = {
        "model": MODEL_ID,
        "component_counts": component_counts,
        "parameter_tables": summarize_parameter_tables(grouped),
        "power_flow_settings": summarize_power_flow_settings(settings),
        "setpoint_summary": {
            "generator_p_set_count": len(generator_p_set),
            "generator_v_set_count": len(generator_v_set),
            "load_p_set_count": len(load_p_set),
            "load_q_set_count": len(load_q_set),
            "total_load_p_mw": sum(float(value) for value in load_p_set.values()),
            "total_load_q_mvar": sum(float(value) for value in load_q_set.values()),
        },
        "power_flow_result": pf_result,
        "power_flow_result_summary": pf_summary,
    }
    export_path = maybe_export_full(full_payload)

    summary = {
        "ok": True,
        **full_payload,
        "full_export_path": export_path,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
