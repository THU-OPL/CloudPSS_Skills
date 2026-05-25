from __future__ import annotations

import csv
import json
import math
import os
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/CloudPSS/IEEE3")
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "transient-stability-margin"
FAULT_DEFINITION = "model/CloudPSS/_newFaultResistor_3p"


def _parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _find_env_values() -> dict[str, str]:
    script_path = Path(__file__).resolve()
    for root in [Path.cwd(), *script_path.parents]:
        values = _parse_env_file(root / ".env")
        if values:
            return values
    return {}


def load_token(token_path: str = ".cloudpss_token") -> str:
    env_values = _find_env_values()
    token = os.environ.get("SIMSTUDIO_TOKEN") or env_values.get("SIMSTUDIO_TOKEN") or env_values.get("CLOUDPSS_TOKEN")
    if token:
        api_url = os.environ.get("CLOUDPSS_API_URL") or env_values.get("CLOUDPSS_API_URL")
        if api_url and not os.environ.get("CLOUDPSS_API_URL"):
            os.environ["CLOUDPSS_API_URL"] = api_url
        return token.strip()

    path = Path(token_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing token file: {path}")
    return path.read_text(encoding="utf-8").strip()


def configure_token(token_path: str = ".cloudpss_token") -> str:
    token = load_token(token_path)
    setToken(token)
    return token


def assert_allowed_model_source(source: str) -> None:
    if "<your-account>" in source:
        raise ValueError("Set CLOUDPSS_TEST_EMT_MODEL_RID or pass an EMT-ready model RID.")
    if source.startswith("model/holdme/"):
        raise ValueError("model/holdme/* is not allowed for live verification")


def load_model_from_source(source: str):
    assert_allowed_model_source(source)
    candidate = Path(source).expanduser()
    if candidate.exists():
        return Model.load(str(candidate))
    return Model.fetch(source)


def _clone_model(model):
    return Model(deepcopy(model.toJSON()))


def wait_for_completion(job, timeout: int = 300, interval: int = 3) -> int:
    start_time = time.time()
    while True:
        status = job.status()
        if status in {1, 2}:
            return status
        if time.time() - start_time > timeout:
            return -1
        time.sleep(interval)


def run_emt(model, *, timeout: int = 300):
    job = model.runEMT()
    final_status = wait_for_completion(job, timeout=timeout)
    if final_status == -1:
        raise TimeoutError("EMT job timed out")
    if final_status == 2:
        raise RuntimeError("EMT job failed")
    if job.result is None:
        raise RuntimeError("EMT result is empty")
    return job


def _normalize(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _component_matches(key: str, comp: Any, selector: str) -> bool:
    target = _normalize(selector)
    args = getattr(comp, "args", {}) or {}
    candidates = [key, getattr(comp, "id", ""), getattr(comp, "label", ""), getattr(comp, "name", "")]
    name_arg = args.get("Name", "")
    if isinstance(name_arg, dict):
        candidates.append(name_arg.get("source", ""))
    else:
        candidates.append(str(name_arg))
    return any(_normalize(candidate) == target for candidate in candidates)


def _find_fault_component_key(model, selector: str | None = None) -> str:
    for key, comp in model.getAllComponents().items():
        if selector and _component_matches(key, comp, selector):
            return key
    for key, comp in model.getAllComponents().items():
        if getattr(comp, "definition", None) == FAULT_DEFINITION:
            return key
    raise ValueError("No _newFaultResistor_3p fault component found")


def _arg_float(comp: Any, arg_name: str, default: float) -> float:
    args = getattr(comp, "args", {}) or {}
    value = args.get(arg_name)
    if isinstance(value, dict):
        value = value.get("source", default)
    if value in {None, ""}:
        return float(default)
    return float(value)


def _apply_fault_duration(model, *, fault_key: str, fault_start: float, clearing_time: float, fault_resistance: float) -> None:
    fault_end = fault_start + clearing_time
    model.updateComponent(
        fault_key,
        args={
            "fs": {"source": f"{fault_start:.12g}", "ɵexp": ""},
            "fe": {"source": f"{fault_end:.12g}", "ɵexp": ""},
            "chg": {"source": f"{fault_resistance:.12g}", "ɵexp": ""},
        },
    )


def _resolve_config(model, config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    scenario = config.get("scenario", {})
    search = config.get("search", {})
    assessment = config.get("assessment", {})
    output = config.get("output", {})
    fault_key = _find_fault_component_key(model, scenario.get("fault_component"))
    fault = model.getAllComponents()[fault_key]
    fault_start = float(scenario.get("fault_start", _arg_float(fault, "fs", 2.5)))
    fault_resistance = float(scenario.get("fault_resistance", _arg_float(fault, "chg", 0.01)))
    coarse = [float(value) for value in search.get("coarse_clearing_times", [0.15, 0.25, 0.4])]
    if not coarse:
        raise ValueError("search.coarse_clearing_times must not be empty")
    coarse = sorted(set(coarse))
    baseline = float(search.get("baseline_clearing_time", coarse[0]))
    return {
        "scenario": {
            "fault_key": fault_key,
            "fault_start": fault_start,
            "fault_resistance": fault_resistance,
            "description": scenario.get("description", "existing fault component clearing-time search"),
        },
        "search": {
            "coarse_clearing_times": coarse,
            "baseline_clearing_time": baseline,
            "bisection_tolerance": float(search.get("bisection_tolerance", 0.01)),
            "max_bisection_iterations": int(search.get("max_bisection_iterations", 8)),
            "timeout": int(search.get("timeout", 300)),
        },
        "assessment": {
            "base_frequency_hz": float(assessment.get("base_frequency_hz", 50.0)),
            "analysis_window": assessment.get("analysis_window"),
            "prefault_window": assessment.get("prefault_window"),
            "postfault_window": assessment.get("postfault_window"),
            "speed_channels": list(assessment.get("speed_channels", [])),
            "frequency_channels": list(assessment.get("frequency_channels", [])),
            "voltage_pu_channels": list(assessment.get("voltage_pu_channels", [])),
            "support_channels": list(assessment.get("support_channels", [])),
            "auto_max_speed_channels": int(assessment.get("auto_max_speed_channels", 3)),
            "max_speed_deviation_pu": float(assessment.get("max_speed_deviation_pu", 0.02)),
            "final_speed_deviation_pu": float(assessment.get("final_speed_deviation_pu", 0.005)),
            "settling_threshold_pu": float(assessment.get("settling_threshold_pu", 0.003)),
            "max_rocof_hz_per_s": float(assessment.get("max_rocof_hz_per_s", 10.0)),
            "voltage_recovery_limit_pu": float(assessment.get("voltage_recovery_limit_pu", 0.9)),
            "rocof_window_samples": max(1, int(assessment.get("rocof_window_samples", 5))),
            "min_samples": int(assessment.get("min_samples", 128)),
        },
        "output": output,
    }


def _plot_name(plot: dict[str, Any], index: int) -> str:
    return plot.get("key") or plot.get("name") or f"plot_{index}"


def _find_trace(result, channel_name: str) -> tuple[int, str, dict[str, list[float]]]:
    for plot_index, plot in enumerate(result.getPlots()):
        if channel_name not in list(result.getPlotChannelNames(plot_index)):
            continue
        data = result.getPlotChannelData(plot_index, channel_name)
        if not data:
            continue
        x_values = [float(value) for value in data.get("x", [])]
        y_values = [float(value) for value in data.get("y", [])]
        if len(x_values) > 1 and len(x_values) == len(y_values):
            return plot_index, _plot_name(plot, plot_index), {"x": x_values, "y": y_values}
    raise KeyError(f"Trace not found: {channel_name}")


def _auto_speed_channels(result, max_channels: int) -> list[str]:
    selected: list[str] = []
    for plot_index, _plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            lower = channel_name.lower()
            if "wr" not in lower and "speed" not in lower and "omega" not in lower:
                continue
            if channel_name not in selected:
                selected.append(channel_name)
            if len(selected) >= max_channels:
                return selected
    return selected


def _window_values(
    x_values: list[float],
    y_values: list[float],
    window: list[float] | tuple[float, float] | None,
    *,
    default_start: float,
    default_end: float,
) -> tuple[list[float], list[float]]:
    if any(x_values[index] >= x_values[index + 1] for index in range(len(x_values) - 1)):
        raise ValueError("Waveform time axis is not strictly increasing")
    if window:
        if len(window) != 2:
            raise ValueError("time window must be [start, end]")
        start = float(window[0])
        end = float(window[1])
    else:
        start = default_start
        end = default_end
    out_x: list[float] = []
    out_y: list[float] = []
    for x_value, y_value in zip(x_values, y_values):
        if start <= x_value <= end:
            out_x.append(x_value)
            out_y.append(y_value)
    return out_x, out_y


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot average empty values")
    return sum(values) / len(values)


def _rms(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot calculate RMS for empty values")
    return math.sqrt(sum(value * value for value in values) / len(values))


def _default_window(times: list[float], *, at_start: bool) -> tuple[float, float]:
    duration = times[-1] - times[0]
    width = max(min(duration * 0.1, 0.5), 0.02)
    if at_start:
        return times[0], min(times[-1], times[0] + width)
    return max(times[0], times[-1] - width), times[-1]


def _settling_time(times: list[float], values: list[float], reference: float, threshold: float) -> float | None:
    for index, current_time in enumerate(times):
        tail = values[index:]
        if tail and all(abs(value - reference) <= threshold for value in tail):
            return current_time
    return None


def _max_rate(times: list[float], values: list[float], window_samples: int) -> tuple[float, float]:
    best_value = 0.0
    best_time = times[0] if times else 0.0
    step = max(1, window_samples)
    for index in range(0, max(0, len(times) - step)):
        dt = times[index + step] - times[index]
        if dt <= 0:
            continue
        value = (values[index + step] - values[index]) / dt
        if abs(value) > abs(best_value):
            best_value = value
            best_time = times[index]
    return best_value, best_time


def _to_pu(values: list[float], kind: str, base_frequency_hz: float) -> list[float]:
    if kind == "frequency":
        return [value / base_frequency_hz for value in values]
    return values


def _analyze_speed_trace(trace: dict[str, list[float]], *, kind: str, config: dict[str, Any]) -> dict[str, Any]:
    x_raw = trace["x"]
    y_raw = _to_pu(trace["y"], kind, config["base_frequency_hz"])
    win_x, win_y = _window_values(x_raw, y_raw, config["analysis_window"], default_start=x_raw[0], default_end=x_raw[-1])
    if len(win_x) < config["min_samples"]:
        raise ValueError(f"Not enough samples in analysis window: {len(win_x)} < {config['min_samples']}")
    prefault_default = _default_window(win_x, at_start=True)
    postfault_default = _default_window(win_x, at_start=False)
    _, prefault_values = _window_values(win_x, win_y, config["prefault_window"], default_start=prefault_default[0], default_end=prefault_default[1])
    _, postfault_values = _window_values(win_x, win_y, config["postfault_window"], default_start=postfault_default[0], default_end=postfault_default[1])
    initial = _mean(prefault_values)
    steady = _mean(postfault_values)
    deviations = [value - initial for value in win_y]
    abs_deviations = [abs(value) for value in deviations]
    max_deviation = max(abs_deviations)
    max_index = abs_deviations.index(max_deviation)
    final_deviation = abs(steady - initial)
    rate_pu, rate_time = _max_rate(win_x, win_y, config["rocof_window_samples"])
    rocof = rate_pu * config["base_frequency_hz"]
    settling = _settling_time(win_x, win_y, steady, config["settling_threshold_pu"])
    stable = (
        max_deviation <= config["max_speed_deviation_pu"]
        and final_deviation <= config["final_speed_deviation_pu"]
        and abs(rocof) <= config["max_rocof_hz_per_s"]
        and settling is not None
    )
    reasons: list[str] = []
    if max_deviation > config["max_speed_deviation_pu"]:
        reasons.append("max_speed_deviation")
    if final_deviation > config["final_speed_deviation_pu"]:
        reasons.append("final_speed_deviation")
    if abs(rocof) > config["max_rocof_hz_per_s"]:
        reasons.append("rocof")
    if settling is None:
        reasons.append("not_settled")
    return {
        "assessment_type": "speed_stability",
        "sample_count": len(win_x),
        "initial_value_pu": initial,
        "steady_value_pu": steady,
        "min_value_pu": min(win_y),
        "max_value_pu": max(win_y),
        "max_speed_deviation_pu": max_deviation,
        "max_speed_deviation_time_s": win_x[max_index],
        "final_speed_deviation_pu": final_deviation,
        "max_rocof_hz_per_s": rocof,
        "max_rocof_time_s": rate_time,
        "settling_time_s": settling,
        "stable": stable,
        "reasons": reasons,
    }


def _analyze_voltage_trace(trace: dict[str, list[float]], *, config: dict[str, Any]) -> dict[str, Any]:
    x_raw = trace["x"]
    y_raw = trace["y"]
    win_x, win_y = _window_values(x_raw, y_raw, config["analysis_window"], default_start=x_raw[0], default_end=x_raw[-1])
    if len(win_x) < config["min_samples"]:
        raise ValueError(f"Not enough samples in voltage window: {len(win_x)} < {config['min_samples']}")
    postfault_default = _default_window(win_x, at_start=False)
    _, postfault_values = _window_values(win_x, win_y, config["postfault_window"], default_start=postfault_default[0], default_end=postfault_default[1])
    recovered = _mean(postfault_values) >= config["voltage_recovery_limit_pu"]
    return {
        "assessment_type": "voltage_recovery",
        "sample_count": len(win_x),
        "min_voltage_pu": min(win_y),
        "steady_voltage_pu": _mean(postfault_values),
        "rms_voltage_pu": _rms(win_y),
        "stable": recovered,
        "reasons": [] if recovered else ["voltage_not_recovered"],
    }


def _analyze_support_trace(trace: dict[str, list[float]], *, config: dict[str, Any]) -> dict[str, Any]:
    x_raw = trace["x"]
    y_raw = trace["y"]
    win_x, win_y = _window_values(x_raw, y_raw, config["analysis_window"], default_start=x_raw[0], default_end=x_raw[-1])
    return {
        "assessment_type": "supporting_waveform",
        "sample_count": len(win_x),
        "min_value": min(win_y),
        "max_value": max(win_y),
        "rms": _rms(win_y),
        "stable": None,
        "reasons": [],
    }


def _evaluate_case(result, assessment: dict[str, Any]) -> dict[str, Any]:
    speed_channels = assessment["speed_channels"] or _auto_speed_channels(result, assessment["auto_max_speed_channels"])
    frequency_channels = assessment["frequency_channels"]
    voltage_channels = assessment["voltage_pu_channels"]
    support_channels = assessment["support_channels"]
    if not speed_channels and not frequency_channels:
        raise RuntimeError("No speed or frequency channels configured or auto-detected")
    channel_rows: list[dict[str, Any]] = []
    for kind, channels in [("speed_pu", speed_channels), ("frequency", frequency_channels)]:
        for channel in channels:
            plot_index, plot, trace = _find_trace(result, channel)
            analysis = _analyze_speed_trace(trace, kind=kind, config=assessment)
            channel_rows.append({"kind": kind, "channel": channel, "plot_index": plot_index, "plot": plot, "analysis": analysis})
    for channel in voltage_channels:
        plot_index, plot, trace = _find_trace(result, channel)
        analysis = _analyze_voltage_trace(trace, config=assessment)
        channel_rows.append({"kind": "voltage_pu", "channel": channel, "plot_index": plot_index, "plot": plot, "analysis": analysis})
    for channel in support_channels:
        plot_index, plot, trace = _find_trace(result, channel)
        analysis = _analyze_support_trace(trace, config=assessment)
        channel_rows.append({"kind": "support", "channel": channel, "plot_index": plot_index, "plot": plot, "analysis": analysis})
    assessed = [row for row in channel_rows if row["analysis"]["stable"] is not None]
    unstable = [row for row in assessed if row["analysis"]["stable"] is False]
    max_speed_dev = max((row["analysis"].get("max_speed_deviation_pu", 0.0) for row in channel_rows), default=0.0)
    max_rocof = max((abs(row["analysis"].get("max_rocof_hz_per_s", 0.0)) for row in channel_rows), default=0.0)
    worst = max(
        [row for row in channel_rows if row["analysis"].get("max_speed_deviation_pu") is not None],
        key=lambda row: row["analysis"].get("max_speed_deviation_pu", 0.0),
        default=None,
    )
    return {
        "stable": bool(assessed) and not unstable,
        "assessed_channel_count": len(assessed),
        "unstable_channel_count": len(unstable),
        "max_speed_deviation_pu": max_speed_dev,
        "max_rocof_hz_per_s": max_rocof,
        "worst_channel": worst["channel"] if worst else "",
        "channels": channel_rows,
    }


def _run_case(base_model, resolved: dict[str, Any], clearing_time: float) -> dict[str, Any]:
    working_model = _clone_model(base_model)
    fault_key = _find_fault_component_key(working_model, resolved["scenario"]["fault_key"])
    _apply_fault_duration(
        working_model,
        fault_key=fault_key,
        fault_start=resolved["scenario"]["fault_start"],
        clearing_time=clearing_time,
        fault_resistance=resolved["scenario"]["fault_resistance"],
    )
    job = run_emt(working_model, timeout=resolved["search"]["timeout"])
    evidence = _evaluate_case(job.result, resolved["assessment"])
    return {
        "clearing_time": clearing_time,
        "fault_start": resolved["scenario"]["fault_start"],
        "fault_end": resolved["scenario"]["fault_start"] + clearing_time,
        "job_id": getattr(job, "id", None),
        **evidence,
    }


def _find_bracket(points: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ordered = sorted(points, key=lambda item: item["clearing_time"])
    stable_points = [point for point in ordered if point["stable"]]
    unstable_points = [point for point in ordered if not point["stable"]]
    if not stable_points:
        return None, unstable_points[0] if unstable_points else None
    lower = stable_points[-1]
    upper_candidates = [point for point in unstable_points if point["clearing_time"] > lower["clearing_time"]]
    return lower, upper_candidates[0] if upper_candidates else None


def _summarize_margin(points: list[dict[str, Any]], baseline: float, cct_seconds: float, relation: str, search_status: str) -> dict[str, Any]:
    stable_points = [point for point in points if point["stable"]]
    unstable_points = [point for point in points if not point["stable"]]
    margin_seconds = cct_seconds - baseline
    margin_percent = margin_seconds / cct_seconds * 100.0 if cct_seconds > 1e-12 else 0.0
    max_speed = max((point["max_speed_deviation_pu"] for point in points), default=0.0)
    max_rocof = max((point["max_rocof_hz_per_s"] for point in points), default=0.0)
    worst = max(points, key=lambda point: point["max_speed_deviation_pu"], default={})
    return {
        "cct_seconds": cct_seconds,
        "cct_relation": relation,
        "search_status": search_status,
        "baseline_clearing_time": baseline,
        "margin_seconds": margin_seconds,
        "margin_percent": margin_percent,
        "stable_points": len(stable_points),
        "unstable_points": len(unstable_points),
        "total_emt_runs": len(points),
        "max_speed_deviation_pu": max_speed,
        "max_rocof_hz_per_s": max_rocof,
        "worst_channel": worst.get("worst_channel", ""),
    }


def _write_artifacts(result_data: dict[str, Any], output_dir: Path, prefix: str, *, generate_report: bool) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output_dir / f"{prefix}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["clearing_time", "fault_end", "stable", "job_id", "max_speed_deviation_pu", "max_rocof_hz_per_s", "worst_channel"])
        for point in result_data["search_points"]:
            writer.writerow(
                [
                    f"{point['clearing_time']:.9g}",
                    f"{point['fault_end']:.9g}",
                    point["stable"],
                    point["job_id"],
                    f"{point['max_speed_deviation_pu']:.9g}",
                    f"{point['max_rocof_hz_per_s']:.9g}",
                    point["worst_channel"],
                ]
            )
    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        summary = result_data["summary"]
        lines = [
            "# Transient Stability Margin Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Fault component key: `{result_data['scenario']['fault_key']}`",
            f"- Fault start: `{result_data['scenario']['fault_start']}` s",
            f"- Fault resistance parameter: `{result_data['scenario']['fault_resistance']}`",
            f"- CCT: `{summary['cct_relation']} {summary['cct_seconds']:.6f} s`",
            f"- Search status: `{summary['search_status']}`",
            f"- Baseline clearing time: `{summary['baseline_clearing_time']:.6f} s`",
            f"- Margin: `{summary['margin_seconds']:.6f} s` / `{summary['margin_percent']:.3f}%`",
            f"- EMT runs: `{summary['total_emt_runs']}`",
            "",
            "| clearing time | stable | max speed dev pu | max RoCoF Hz/s | job id |",
            "| ---: | --- | ---: | ---: | --- |",
        ]
        for point in result_data["search_points"]:
            lines.append(
                f"| {point['clearing_time']:.6f} | {point['stable']} | "
                f"{point['max_speed_deviation_pu']:.6f} | {point['max_rocof_hz_per_s']:.6f} | `{point['job_id']}` |"
            )
        lines.extend(
            [
                "",
                "## Engineering Notes",
                "",
                "- CCT is estimated from real CloudPSS EMT runs and configured waveform criteria.",
                "- `>=` means no unstable upper bound was found in the configured scan range.",
                "- This is a transient stability screening result, not a formal standards-compliance certification.",
                "- Review fault modeling, protection actions, monitored generator coverage, and voltage criteria before engineering sign-off.",
            ]
        )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = Path("")
    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "markdown_path": str(markdown_path) if markdown_path else "",
    }


def run_transient_stability_margin(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = _resolve_config(model, config)
    points: list[dict[str, Any]] = []
    for clearing_time in resolved["search"]["coarse_clearing_times"]:
        points.append(_run_case(model, resolved, clearing_time))
    lower, upper = _find_bracket(points)
    relation = "="
    search_status = "bounded_bisection"
    if lower is not None and upper is not None:
        left = lower["clearing_time"]
        right = upper["clearing_time"]
        iterations = 0
        while right - left > resolved["search"]["bisection_tolerance"] and iterations < resolved["search"]["max_bisection_iterations"]:
            mid = (left + right) / 2.0
            point = _run_case(model, resolved, mid)
            points.append(point)
            if point["stable"]:
                left = mid
            else:
                right = mid
            iterations += 1
        cct_seconds = (left + right) / 2.0
    elif lower is not None:
        relation = ">="
        search_status = "stable_through_upper_bound"
        cct_seconds = lower["clearing_time"]
    elif upper is not None:
        relation = "<="
        search_status = "unstable_at_lower_bound"
        cct_seconds = upper["clearing_time"]
    else:
        raise RuntimeError("No search points were evaluated")
    points_sorted = sorted(points, key=lambda item: item["clearing_time"])
    summary = _summarize_margin(points_sorted, resolved["search"]["baseline_clearing_time"], cct_seconds, relation, search_status)
    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "scenario": resolved["scenario"],
        "search": resolved["search"],
        "assessment": resolved["assessment"],
        "summary": summary,
        "search_points": points_sorted,
    }
    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "transient_stability_margin")
    artifacts = _write_artifacts(result_data, target_dir, prefix, generate_report=bool(output_config.get("generate_report", True)))
    return {**result_data, "artifacts": artifacts}
