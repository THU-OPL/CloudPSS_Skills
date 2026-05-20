from __future__ import annotations

import json
import os
import statistics
import sys
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


MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/CloudPSS/IEEE39")
FLOW_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")
MIN_BUS_COUNT = int(os.environ.get("CLOUDPSS_TEST_MIN_BUS_COUNT", "39"))


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def build_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=MODEL_ID)
    log(f"init-done result={result}")
    return sa


def summarize_results(sa: PowerSystemAnalysis) -> dict[str, Any]:
    bus_rows = sa.get_bus_all_pf_result()
    line_rows = sa.get_acline_all_pf_result()
    gen_result = sa.get_generator_all_pf_result()
    voltages = [float(row[2]) for row in bus_rows]
    line_losses = [float(row[3]) + float(row[5]) for row in line_rows]
    branch_stress = [
        {
            "line_key": row[0],
            "from_bus": row[1],
            "to_bus": row[2],
            "p_from_mw": float(row[3]),
            "q_from_mvar": float(row[4]),
            "p_to_mw": float(row[5]),
            "q_to_mvar": float(row[6]),
            "active_loss_mw": float(row[3]) + float(row[5]),
            "max_end_mva": max(
                (float(row[3]) ** 2 + float(row[4]) ** 2) ** 0.5,
                (float(row[5]) ** 2 + float(row[6]) ** 2) ** 0.5,
            ),
        }
        for row in line_rows
    ]
    gen_p = [float(value) for value in gen_result[2]]
    gen_q = [float(value) for value in gen_result[3]]
    return {
        "bus_count": len(bus_rows),
        "line_count": len(line_rows),
        "generator_count": len(gen_result[0]),
        "v_min_pu": min(voltages),
        "v_max_pu": max(voltages),
        "v_avg_pu": statistics.fmean(voltages),
        "voltage_low_count": sum(1 for value in voltages if value < 0.95),
        "voltage_high_count": sum(1 for value in voltages if value > 1.05),
        "total_active_loss_mw": sum(line_losses),
        "total_gen_p_mw": sum(gen_p),
        "total_gen_q_mvar": sum(gen_q),
        "top_branch_stress": sorted(
            branch_stress,
            key=lambda row: abs(row["max_end_mva"]),
            reverse=True,
        )[:5],
    }


def run_random_sample(name: str, *, p_low: float, p_high: float, v_low: float = 1.0, v_high: float = 1.0) -> dict[str, Any]:
    log(f"scenario {name} start")
    sa = build_case()
    result = sa.power_flow_sample_simple_ramdom(
        flowJobName=FLOW_JOB_NAME,
        flowConfigname=CONFIG_NAME,
        P_low=p_low,
        P_high=p_high,
        V_low=v_low,
        V_high=v_high,
    )
    if result.get("status") != "success":
        raise RuntimeError(f"Power flow scenario {name} failed: {result}")
    summary = summarize_results(sa)
    log(f"scenario {name} done")
    return {
        "name": name,
        "kind": "random_sample",
        "settings": {"P_low": p_low, "P_high": p_high, "V_low": v_low, "V_high": v_high},
        "power_flow": result,
        "metrics": summary,
    }


def run_load_scale(name: str, scale: float) -> dict[str, Any]:
    log(f"scenario {name} start")
    sa = build_case()
    baseline_runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    base_load_p = sa.get_load_all_p_set()
    base_load_q = sa.get_load_all_q_set()
    scaled_p = [float(value) * scale for value in base_load_p.values()]
    scaled_q = [float(value) * scale for value in base_load_q.values()]
    sa.set_load_all_p_set(scaled_p)
    sa.set_load_all_q_set(scaled_q)
    runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    summary = summarize_results(sa)
    log(f"scenario {name} done")
    return {
        "name": name,
        "kind": "load_scale",
        "settings": {"load_scale": scale},
        "baseline_runner_id": baseline_runner_id,
        "runner_id": runner_id,
        "base_total_load_p_mw": sum(float(value) for value in base_load_p.values()),
        "adjusted_total_load_p_mw": sum(scaled_p),
        "metrics": summary,
    }


def run_generator_voltage(name: str, setpoint: float) -> dict[str, Any]:
    log(f"scenario {name} start")
    sa = build_case()
    baseline_runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    base_gen_v = sa.get_generator_all_v_set()
    new_vset = [setpoint] * len(base_gen_v)
    sa.set_generator_all_v_set(new_vset)
    runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    summary = summarize_results(sa)
    log(f"scenario {name} done")
    return {
        "name": name,
        "kind": "generator_voltage_setpoint",
        "settings": {"generator_v_setpoint": setpoint},
        "baseline_runner_id": baseline_runner_id,
        "runner_id": runner_id,
        "base_avg_setpoint_pu": statistics.fmean(float(value) for value in base_gen_v.values()),
        "adjusted_avg_setpoint_pu": statistics.fmean(new_vset),
        "metrics": summary,
    }


def compare_to_baseline(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = scenarios[0]["metrics"]
    comparison: list[dict[str, Any]] = []
    for scenario in scenarios:
        metrics = scenario["metrics"]
        comparison.append(
            {
                "name": scenario["name"],
                "delta_v_min_pu": metrics["v_min_pu"] - baseline["v_min_pu"],
                "delta_v_avg_pu": metrics["v_avg_pu"] - baseline["v_avg_pu"],
                "delta_total_active_loss_mw": metrics["total_active_loss_mw"] - baseline["total_active_loss_mw"],
                "delta_total_gen_p_mw": metrics["total_gen_p_mw"] - baseline["total_gen_p_mw"],
            }
        )
    return comparison


def main() -> None:
    scenarios = [
        run_random_sample("baseline_flat", p_low=1.0, p_high=1.0),
        run_load_scale("load_90pct", 0.9),
        run_load_scale("load_110pct", 1.1),
        run_generator_voltage("generator_voltage_1_04", 1.04),
        run_random_sample("random_load_95_105pct", p_low=0.95, p_high=1.05, v_low=0.99, v_high=1.01),
    ]

    for scenario in scenarios:
        metrics = scenario["metrics"]
        if metrics["bus_count"] < MIN_BUS_COUNT:
            raise RuntimeError(f"Scenario {scenario['name']} has unexpected bus count: {metrics['bus_count']}")
        if metrics["line_count"] == 0:
            raise RuntimeError(f"Scenario {scenario['name']} has no line results")

    rankings = {
        "lowest_voltage_first": [
            {"name": s["name"], "v_min_pu": s["metrics"]["v_min_pu"]}
            for s in sorted(scenarios, key=lambda item: item["metrics"]["v_min_pu"])
        ],
        "highest_voltage_first": [
            {"name": s["name"], "v_max_pu": s["metrics"]["v_max_pu"]}
            for s in sorted(scenarios, key=lambda item: item["metrics"]["v_max_pu"], reverse=True)
        ],
        "highest_loss_first": [
            {"name": s["name"], "total_active_loss_mw": s["metrics"]["total_active_loss_mw"]}
            for s in sorted(scenarios, key=lambda item: item["metrics"]["total_active_loss_mw"], reverse=True)
        ],
    }

    print(
        json.dumps(
            {
                "ok": True,
                "model": MODEL_ID,
                "scenario_count": len(scenarios),
                "scenarios": scenarios,
                "comparison": compare_to_baseline(scenarios),
                "rankings": rankings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

