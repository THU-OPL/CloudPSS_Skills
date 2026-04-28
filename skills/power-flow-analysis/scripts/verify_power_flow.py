from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis


ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


MODEL_ID = "model/yuanxuefeng/IEEE39"
JOB_NAME = "SA_潮流计算"
CONFIG_NAME = "SA_参数方案"


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def summarize_bus(bus_rows: list[list[Any]]) -> dict[str, float]:
    voltages = [float(row[2]) for row in bus_rows]
    return {
        "bus_count": len(bus_rows),
        "v_min": min(voltages),
        "v_max": max(voltages),
        "v_avg": statistics.fmean(voltages),
    }


def summarize_line(line_rows: list[list[Any]]) -> dict[str, float]:
    total_loss = sum(float(row[3]) + float(row[5]) for row in line_rows)
    return {
        "line_count": len(line_rows),
        "total_active_loss_mw": total_loss,
    }


def summarize_generator(gen_result: list[list[Any]]) -> dict[str, float]:
    gen_keys, gen_v, gen_p, gen_q = gen_result
    return {
        "generator_count": len(gen_keys),
        "total_gen_p_mw": sum(float(value) for value in gen_p),
        "total_gen_q_mvar": sum(float(value) for value in gen_q),
        "avg_gen_v_pu": statistics.fmean(float(value) for value in gen_v),
    }


def build_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=MODEL_ID)
    log(f"init-done result={result}")
    return sa


def collect_power_flow_results(sa: PowerSystemAnalysis) -> dict[str, Any]:
    bus_rows = sa.get_bus_all_pf_result()
    line_rows = sa.get_acline_all_pf_result()
    gen_result = sa.get_generator_all_pf_result()
    return {
        "bus_summary": summarize_bus(bus_rows),
        "line_summary": summarize_line(line_rows),
        "generator_summary": summarize_generator(gen_result),
    }


def run_random_sample(sa: PowerSystemAnalysis) -> dict[str, Any]:
    result = sa.power_flow_sample_simple_ramdom(
        flowJobName=JOB_NAME,
        flowConfigname=CONFIG_NAME,
        P_low=1.0,
        P_high=1.0,
        V_low=1.0,
        V_high=1.0,
    )
    if result.get("status") != "success":
        raise RuntimeError(f"Power flow did not converge: {result}")

    summary = collect_power_flow_results(sa)
    summary["power_flow"] = result
    return summary


def run_current_state(sa: PowerSystemAnalysis) -> dict[str, Any]:
    runner_id = sa.runProject(jobName=JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    summary = collect_power_flow_results(sa)
    summary["runner_id"] = runner_id
    return summary


def scenario_basic() -> dict[str, Any]:
    log("scenario basic start")
    sa = build_case()
    summary = run_random_sample(sa)
    log("scenario basic done")
    return summary


def scenario_load_increase() -> dict[str, Any]:
    log("scenario load-increase start")
    sa = build_case()
    baseline = run_current_state(sa)

    base_load_p = sa.get_load_all_p_set()
    base_load_q = sa.get_load_all_q_set()
    scaled_p = [float(value) * 1.2 for value in base_load_p.values()]
    scaled_q = [float(value) * 1.2 for value in base_load_q.values()]

    sa.set_load_all_p_set(scaled_p)
    sa.set_load_all_q_set(scaled_q)
    adjusted = run_current_state(sa)

    log("scenario load-increase done")
    return {
        "baseline": baseline,
        "adjusted": adjusted,
        "base_total_load_p_mw": sum(float(value) for value in base_load_p.values()),
        "adjusted_total_load_p_mw": sum(scaled_p),
        "voltage_delta_min_pu": adjusted["bus_summary"]["v_min"] - baseline["bus_summary"]["v_min"],
    }


def scenario_voltage_adjustment() -> dict[str, Any]:
    log("scenario voltage-adjustment start")
    sa = build_case()
    baseline = run_current_state(sa)

    base_gen_v = sa.get_generator_all_v_set()
    new_vset = [1.05] * len(base_gen_v)
    sa.set_generator_all_v_set(new_vset)
    adjusted = run_current_state(sa)

    log("scenario voltage-adjustment done")
    return {
        "baseline": baseline,
        "adjusted": adjusted,
        "base_avg_setpoint_pu": statistics.fmean(float(value) for value in base_gen_v.values()),
        "adjusted_avg_setpoint_pu": statistics.fmean(new_vset),
        "voltage_delta_avg_pu": adjusted["bus_summary"]["v_avg"] - baseline["bus_summary"]["v_avg"],
    }


def main() -> None:
    summary = {
        "basic": scenario_basic(),
        "load_increase_20pct": scenario_load_increase(),
        "generator_voltage_to_1_05": scenario_voltage_adjustment(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
