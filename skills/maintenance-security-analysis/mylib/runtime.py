from __future__ import annotations

import os
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
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
SCREEN_LIMIT = int(os.environ.get("CLOUDPSS_MAINTENANCE_SECURITY_LIMIT", "2"))
VOLTAGE_MIN = float(os.environ.get("CLOUDPSS_SECURITY_VMIN", "0.95"))
VOLTAGE_MAX = float(os.environ.get("CLOUDPSS_SECURITY_VMAX", "1.05"))


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def build_case(model_id: str) -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={model_id}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=model_id)
    log(f"init-done result={result}")
    return sa


def read_numeric(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("source")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def branch_rows(sa: PowerSystemAnalysis) -> list[dict[str, Any]]:
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
                "max_end_mva": max(
                    (p_from**2 + q_from**2) ** 0.5,
                    (p_to**2 + q_to**2) ** 0.5,
                ),
            }
        )
    return rows


def summarize_case(sa: PowerSystemAnalysis) -> dict[str, Any]:
    bus_rows = sa.get_bus_all_pf_result()
    branches = branch_rows(sa)
    voltages = [float(row[2]) for row in bus_rows]
    voltage_violations = [
        {
            "bus_key": row[0],
            "bus_label": row[1],
            "voltage_pu": float(row[2]),
            "limit": f"<{VOLTAGE_MIN}" if float(row[2]) < VOLTAGE_MIN else f">{VOLTAGE_MAX}",
        }
        for row in bus_rows
        if float(row[2]) < VOLTAGE_MIN or float(row[2]) > VOLTAGE_MAX
    ]
    return {
        "bus_count": len(bus_rows),
        "line_count": len(branches),
        "v_min_pu": min(voltages),
        "v_max_pu": max(voltages),
        "v_avg_pu": statistics.fmean(voltages),
        "voltage_violation_count": len(voltage_violations),
        "sample_voltage_violations": voltage_violations[:10],
        "total_active_loss_mw": sum(row["active_loss_mw"] for row in branches),
        "top_branch_stress": sorted(branches, key=lambda item: abs(item["max_end_mva"]), reverse=True)[:5],
        "top_loss_branches": sorted(branches, key=lambda item: abs(item["active_loss_mw"]), reverse=True)[:5],
    }


def line_metadata(sa: PowerSystemAnalysis, line_key: str) -> dict[str, Any]:
    comp = sa.project.getComponentByKey(line_key)
    args = getattr(comp, "args", {}) or {}
    label = getattr(comp, "label", None) or args.get("Name") or line_key
    irated = read_numeric(args.get("Irated"))
    vbase = read_numeric(args.get("Vbase"))
    rating_mva = 1.7320508075688772 * vbase * irated if irated and vbase else None
    return {
        "line_key": line_key,
        "label": label,
        "definition": getattr(comp, "definition", None),
        "pins": dict(getattr(comp, "pins", {}) or {}),
        "rating_mva": rating_mva,
    }


def remove_line(sa: PowerSystemAnalysis, line_key: str) -> dict[str, Any]:
    comp = sa.project.getComponentByKey(line_key)
    original_pins = dict(getattr(comp, "pins", {}) or {})
    before_count = len(sa.project.getAllComponents())
    removed = sa.project.removeComponent(line_key)
    after_count = len(sa.project.getAllComponents())
    return {
        "line_key": line_key,
        "original_pins": original_pins,
        "remove_return": removed,
        "component_count_before": before_count,
        "component_count_after": after_count,
    }


def thermal_summary(sa: PowerSystemAnalysis) -> dict[str, Any]:
    supported = 0
    unsupported = 0
    max_loading: dict[str, Any] | None = None
    for row in branch_rows(sa):
        try:
            metadata = line_metadata(sa, str(row["line_key"]))
        except Exception:
            unsupported += 1
            continue
        rating = metadata.get("rating_mva")
        if not rating:
            unsupported += 1
            continue
        supported += 1
        loading = abs(row["max_end_mva"]) / rating
        candidate = {
            "line_key": row["line_key"],
            "label": metadata.get("label"),
            "loading_pu": loading,
            "loading_percent": loading * 100,
            "rating_mva": rating,
            "max_end_mva": row["max_end_mva"],
        }
        if max_loading is None or candidate["loading_pu"] > max_loading["loading_pu"]:
            max_loading = candidate
    return {
        "thermal_supported_count": supported,
        "thermal_unsupported_count": unsupported,
        "max_loading": max_loading,
    }


def severity(case_summary: dict[str, Any], reference_summary: dict[str, Any], converged: bool) -> float:
    if not converged:
        return 1.0
    score = 0.0
    if case_summary["v_min_pu"] < VOLTAGE_MIN:
        score = max(score, min((VOLTAGE_MIN - case_summary["v_min_pu"]) / VOLTAGE_MIN, 1.0))
    if case_summary["v_max_pu"] > VOLTAGE_MAX:
        score = max(score, min((case_summary["v_max_pu"] - VOLTAGE_MAX) / max(1.1 - VOLTAGE_MAX, 0.001), 1.0))
    if case_summary["voltage_violation_count"]:
        score = max(score, min(0.2 + case_summary["voltage_violation_count"] * 0.02, 1.0))
    reference_loss = abs(reference_summary["total_active_loss_mw"])
    if reference_loss:
        loss_delta_ratio = abs(case_summary["total_active_loss_mw"] - reference_summary["total_active_loss_mw"]) / reference_loss
        score = max(score, min(loss_delta_ratio, 1.0))
    return round(score, 4)


def run_power_flow_case(model_id: str, outage_keys: list[str]) -> dict[str, Any]:
    sa = build_case(model_id)
    candidate_lines = [str(key) for key in sa.get_acline_all_keys().tolist()]
    outage_actions = []
    outage_metadata = []
    for line_key in outage_keys:
        outage_metadata.append(line_metadata(sa, line_key))
        outage_actions.append(remove_line(sa, line_key))
    runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    if runner_id == -1:
        raise RuntimeError("CloudPSS runner returned failed status")
    case_summary = summarize_case(sa)
    case_summary["runner_id"] = runner_id
    case_summary["thermal"] = thermal_summary(sa)
    return {
        "sa": sa,
        "candidate_lines": candidate_lines,
        "outage_metadata": outage_metadata,
        "outage_actions": outage_actions,
        "summary": case_summary,
    }


def run_residual_contingency(
    model_id: str,
    maintenance_line_key: str,
    contingency_line_key: str,
    maintenance_summary: dict[str, Any],
) -> dict[str, Any]:
    log(f"residual-contingency maintenance={maintenance_line_key} contingency={contingency_line_key} start")
    try:
        case = run_power_flow_case(model_id, [maintenance_line_key, contingency_line_key])
        case_summary = case["summary"]
        result = {
            "maintenance_line": case["outage_metadata"][0],
            "contingency_line": case["outage_metadata"][1],
            "outage_actions": case["outage_actions"],
            "status": "converged",
            "converged": True,
            "case_summary": case_summary,
            "severity": severity(case_summary, maintenance_summary, True),
            "delta_v_min_pu": case_summary["v_min_pu"] - maintenance_summary["v_min_pu"],
            "delta_total_active_loss_mw": case_summary["total_active_loss_mw"] - maintenance_summary["total_active_loss_mw"],
        }
    except Exception as exc:
        result = {
            "maintenance_line_key": maintenance_line_key,
            "contingency_line_key": contingency_line_key,
            "status": "failed",
            "converged": False,
            "error": str(exc),
            "severity": 1.0,
        }
    log(f"residual-contingency maintenance={maintenance_line_key} contingency={contingency_line_key} done status={result['status']}")
    return result


def run_maintenance_security_analysis(
    *,
    model_id: str = MODEL_ID,
    maintenance_line_key: str | None = None,
    limit: int = SCREEN_LIMIT,
) -> dict[str, Any]:
    normal_case = run_power_flow_case(model_id, [])
    candidate_lines = normal_case["candidate_lines"]
    if not candidate_lines:
        raise RuntimeError("No candidate AC lines discovered")

    selected_maintenance = maintenance_line_key or os.environ.get("CLOUDPSS_MAINTENANCE_LINE_KEY") or candidate_lines[0]
    if selected_maintenance not in candidate_lines:
        raise ValueError(f"Maintenance line is not in candidate AC lines: {selected_maintenance}")

    maintenance_case = run_power_flow_case(model_id, [selected_maintenance])
    maintenance_summary = maintenance_case["summary"]
    residual_candidates = [key for key in candidate_lines if key != selected_maintenance][: max(1, limit)]
    residual_contingencies = [
        run_residual_contingency(model_id, selected_maintenance, contingency_key, maintenance_summary)
        for contingency_key in residual_candidates
    ]
    if not residual_contingencies:
        raise RuntimeError("No residual contingency scenarios were attempted")

    ranking = sorted(
        [
            {
                "contingency_line_key": item.get("contingency_line", {}).get("line_key", item.get("contingency_line_key")),
                "label": item.get("contingency_line", {}).get("label"),
                "status": item["status"],
                "severity": item["severity"],
                "voltage_violation_count": item.get("case_summary", {}).get("voltage_violation_count"),
                "delta_v_min_pu": item.get("delta_v_min_pu"),
                "delta_total_active_loss_mw": item.get("delta_total_active_loss_mw"),
                "error": item.get("error"),
            }
            for item in residual_contingencies
        ],
        key=lambda item: item["severity"],
        reverse=True,
    )

    return {
        "ok": True,
        "model": model_id,
        "flow_job": FLOW_JOB_NAME,
        "config": CONFIG_NAME,
        "voltage_limits": {"min": VOLTAGE_MIN, "max": VOLTAGE_MAX},
        "candidate_line_count": len(candidate_lines),
        "maintenance_line": maintenance_case["outage_metadata"][0],
        "normal_case": normal_case["summary"],
        "maintenance_case": {
            "outage_action": maintenance_case["outage_actions"][0],
            "summary": maintenance_summary,
            "delta_v_min_pu": maintenance_summary["v_min_pu"] - normal_case["summary"]["v_min_pu"],
            "delta_total_active_loss_mw": maintenance_summary["total_active_loss_mw"] - normal_case["summary"]["total_active_loss_mw"],
        },
        "residual_screened_line_count": len(residual_candidates),
        "residual_contingencies": residual_contingencies,
        "residual_severity_ranking": ranking,
        "unsupported": {
            "maintenance_modeling_note": "Maintenance and residual contingency outages are modeled by removing line components from local working copies before real CloudPSS power-flow runs.",
            "thermal_note": "Thermal percentage is reported only when Irated and Vbase are available on line components.",
        },
    }
