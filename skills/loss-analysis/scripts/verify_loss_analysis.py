from __future__ import annotations

import json
import os
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


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def build_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=MODEL_ID)
    log(f"init-done result={result}")
    return sa


def branch_loss_rows(sa: PowerSystemAnalysis) -> list[dict[str, Any]]:
    rows = []
    for row in sa.get_acline_all_pf_result():
        p_from = float(row[3])
        q_from = float(row[4])
        p_to = float(row[5])
        q_to = float(row[6])
        rows.append(
            {
                "line_key": row[0],
                "from_bus": row[1],
                "to_bus": row[2],
                "p_from_mw": p_from,
                "q_from_mvar": q_from,
                "p_to_mw": p_to,
                "q_to_mvar": q_to,
                "active_loss_mw": p_from + p_to,
                "reactive_loss_mvar": q_from + q_to,
                "max_end_mva": max(
                    (p_from**2 + q_from**2) ** 0.5,
                    (p_to**2 + q_to**2) ** 0.5,
                ),
            }
        )
    return rows


def summarize_losses(sa: PowerSystemAnalysis) -> dict[str, Any]:
    branches = branch_loss_rows(sa)
    gen_result = sa.get_generator_all_pf_result()
    load_p = sa.get_load_all_p_set()
    load_q = sa.get_load_all_q_set()
    total_active_loss = sum(row["active_loss_mw"] for row in branches)
    total_reactive_loss = sum(row["reactive_loss_mvar"] for row in branches)
    total_gen_p = sum(float(value) for value in gen_result[2])
    total_gen_q = sum(float(value) for value in gen_result[3])
    total_load_p = sum(float(value) for value in load_p.values())
    total_load_q = sum(float(value) for value in load_q.values())
    top_loss = sorted(branches, key=lambda row: abs(row["active_loss_mw"]), reverse=True)[:10]
    top_stress = sorted(branches, key=lambda row: abs(row["max_end_mva"]), reverse=True)[:10]
    return {
        "line_count": len(branches),
        "generator_count": len(gen_result[0]),
        "total_active_loss_mw": total_active_loss,
        "total_reactive_loss_mvar": total_reactive_loss,
        "total_gen_p_mw": total_gen_p,
        "total_gen_q_mvar": total_gen_q,
        "total_load_p_mw": total_load_p,
        "total_load_q_mvar": total_load_q,
        "loss_percent_of_generation": (total_active_loss / total_gen_p * 100) if total_gen_p else None,
        "loss_percent_of_load": (total_active_loss / total_load_p * 100) if total_load_p else None,
        "top_loss_branches": top_loss,
        "top_stress_branches": top_stress,
    }


def run_base_case() -> dict[str, Any]:
    log("base-case start")
    sa = build_case()
    runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    summary = summarize_losses(sa)
    log("base-case done")
    return {"runner_id": runner_id, **summary}


def run_load_scale(scale: float) -> dict[str, Any]:
    log(f"load-scale {scale} start")
    sa = build_case()
    base_load_p = sa.get_load_all_p_set()
    base_load_q = sa.get_load_all_q_set()
    sa.set_load_all_p_set([float(value) * scale for value in base_load_p.values()])
    sa.set_load_all_q_set([float(value) * scale for value in base_load_q.values()])
    runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    summary = summarize_losses(sa)
    log(f"load-scale {scale} done")
    return {"load_scale": scale, "runner_id": runner_id, **summary}


def build_recommendations(base_case: dict[str, Any], sensitivity: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    top_loss = base_case["top_loss_branches"][0] if base_case["top_loss_branches"] else None
    if top_loss:
        recommendations.append(
            f"优先复核支路 {top_loss['line_key']} ({top_loss['from_bus']} -> {top_loss['to_bus']})，"
            f"其有功损耗约 {top_loss['active_loss_mw']:.4f} MW。"
        )
    if len(sensitivity) >= 2:
        low = min(sensitivity, key=lambda item: item["load_scale"])
        high = max(sensitivity, key=lambda item: item["load_scale"])
        delta_loss = high["total_active_loss_mw"] - low["total_active_loss_mw"]
        delta_load = high["total_load_p_mw"] - low["total_load_p_mw"]
        if delta_load:
            recommendations.append(
                f"负荷从 {low['load_scale']:.2f} 到 {high['load_scale']:.2f} 时，"
                f"网损变化率约 {delta_loss / delta_load:.6f} MW/MW。"
            )
    recommendations.append("该分析未执行 OPF；若需要定量降损方案，应进一步做无功优化或潮流优化。")
    return recommendations


def main() -> None:
    base_case = run_base_case()
    if base_case["line_count"] == 0:
        raise RuntimeError("No line results available for loss analysis")

    sensitivity = [run_load_scale(scale) for scale in [0.9, 1.0, 1.1]]
    if any(item["line_count"] == 0 for item in sensitivity):
        raise RuntimeError(f"Missing branch results in sensitivity cases: {sensitivity}")

    sorted_sensitivity = sorted(sensitivity, key=lambda item: item["load_scale"])
    base_loss = next(item for item in sorted_sensitivity if item["load_scale"] == 1.0)["total_active_loss_mw"]
    load_sensitivity = [
        {
            "load_scale": item["load_scale"],
            "total_load_p_mw": item["total_load_p_mw"],
            "total_active_loss_mw": item["total_active_loss_mw"],
            "delta_loss_vs_1_0_mw": item["total_active_loss_mw"] - base_loss,
            "loss_percent_of_generation": item["loss_percent_of_generation"],
        }
        for item in sorted_sensitivity
    ]

    print(
        json.dumps(
            {
                "ok": True,
                "model": MODEL_ID,
                "base_case": base_case,
                "load_sensitivity": load_sensitivity,
                "recommendations": build_recommendations(base_case, sorted_sensitivity),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

