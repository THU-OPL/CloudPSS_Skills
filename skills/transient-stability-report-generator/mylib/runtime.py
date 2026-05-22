from __future__ import annotations

import csv
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/CloudPSS/IEEE3")
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "transient-stability-report-generator"


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


def _plot_name(plot: dict[str, Any], index: int) -> str:
    return plot.get("key") or plot.get("name") or f"plot_{index}"


def _resolve_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    assessment = config.get("assessment", config.get("analysis", {}))
    channels = config.get("channels", {})
    output = config.get("output", {})
    return {
        "base_frequency_hz": float(assessment.get("base_frequency_hz", assessment.get("base_frequency", 50.0))),
        "analysis_window": assessment.get("analysis_window"),
        "prefault_window": assessment.get("prefault_window"),
        "postfault_window": assessment.get("postfault_window"),
        "settling_threshold_pu": float(assessment.get("settling_threshold_pu", assessment.get("settling_time_threshold", 0.002))),
        "max_speed_deviation_pu": float(assessment.get("max_speed_deviation_pu", assessment.get("max_speed_deviation", 0.02))),
        "rocof_window_samples": max(1, int(assessment.get("rocof_window_samples", 5))),
        "voltage_low_limit_pu": float(assessment.get("voltage_low_limit_pu", 0.8)),
        "voltage_recovery_limit_pu": float(assessment.get("voltage_recovery_limit_pu", 0.9)),
        "assess_voltage_channels": bool(assessment.get("assess_voltage_channels", False)),
        "min_samples": int(assessment.get("min_samples", 128)),
        "auto_max_channels": int(channels.get("auto_max_channels", 3)),
        "channels": {
            "speed_pu": list(channels.get("speed_pu", [])),
            "frequency": list(channels.get("frequency", [])),
            "voltage_pu": list(channels.get("voltage_pu", [])),
            "voltage": list(channels.get("voltage", [])),
            "power": list(channels.get("power", [])),
            "angle": list(channels.get("angle", [])),
            "generic": list(channels.get("generic", [])),
        },
        "report": config.get("report", {}),
        "output": output,
    }


def _find_trace(result, channel_name: str) -> tuple[int, str, dict[str, list[float]]]:
    for plot_index, plot in enumerate(result.getPlots()):
        channel_names = list(result.getPlotChannelNames(plot_index))
        if channel_name not in channel_names:
            continue
        data = result.getPlotChannelData(plot_index, channel_name)
        if not data:
            continue
        x_values = [float(value) for value in data.get("x", [])]
        y_values = [float(value) for value in data.get("y", [])]
        if len(x_values) > 1 and len(x_values) == len(y_values):
            return plot_index, _plot_name(plot, plot_index), {"x": x_values, "y": y_values}
    raise KeyError(f"Trace not found: {channel_name}")


def _looks_like_channel(channel_name: str, kind: str) -> bool:
    lower = channel_name.lower()
    if kind == "speed_pu":
        return "wr" in lower or "speed" in lower or "omega" in lower
    if kind == "voltage":
        return lower.startswith("v") or "vac" in lower or "vrms" in lower
    if kind == "voltage_pu":
        return "vrms" in lower or "vpu" in lower or "voltage_pu" in lower
    if kind == "power":
        return lower.startswith("#p") or ".p" in lower
    if kind == "angle":
        return "theta" in lower or "angle" in lower or "delta" in lower
    return False


def _auto_select_traces(result, auto_max_channels: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for kind in ["speed_pu", "voltage", "power", "angle"]:
        count = 0
        for plot_index, plot in enumerate(result.getPlots()):
            for channel_name in result.getPlotChannelNames(plot_index):
                if count >= auto_max_channels:
                    break
                if not _looks_like_channel(channel_name, kind):
                    continue
                data = result.getPlotChannelData(plot_index, channel_name)
                if not data:
                    continue
                x_values = [float(value) for value in data.get("x", [])]
                y_values = [float(value) for value in data.get("y", [])]
                if len(x_values) > 1 and len(x_values) == len(y_values):
                    selected.append(
                        {
                            "kind": kind,
                            "channel": channel_name,
                            "plot_index": plot_index,
                            "plot": _plot_name(plot, plot_index),
                            "trace": {"x": x_values, "y": y_values},
                        }
                    )
                    count += 1
            if count >= auto_max_channels:
                break
    if not selected:
        raise RuntimeError("No transient stability report channels available")
    return selected


def _select_traces(result, channel_config: dict[str, list[str]], auto_max_channels: int) -> list[dict[str, Any]]:
    requested = [(kind, name) for kind, names in channel_config.items() for name in names]
    if not requested:
        return _auto_select_traces(result, auto_max_channels)

    selected: list[dict[str, Any]] = []
    for kind, channel_name in requested:
        plot_index, plot, trace = _find_trace(result, channel_name)
        selected.append(
            {
                "kind": kind,
                "channel": channel_name,
                "plot_index": plot_index,
                "plot": plot,
                "trace": trace,
            }
        )
    return selected


def _window_values(
    x_values: list[float],
    y_values: list[float],
    window: list[float] | tuple[float, float] | None,
    *,
    default_start: float,
    default_end: float,
) -> tuple[list[float], list[float]]:
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


def _validate_time_axis(x_values: list[float]) -> None:
    if any(x_values[index] >= x_values[index + 1] for index in range(len(x_values) - 1)):
        raise ValueError("Waveform time axis is not strictly increasing")


def _default_short_window(times: list[float], *, at_start: bool) -> tuple[float, float]:
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


def _max_rate(times: list[float], values: list[float], window_samples: int) -> dict[str, float]:
    if len(times) < 2:
        return {"value": 0.0, "time_s": times[0] if times else 0.0}
    best_value = 0.0
    best_time = times[0]
    step = max(1, window_samples)
    for index in range(0, len(times) - step):
        dt = times[index + step] - times[index]
        if dt <= 0:
            continue
        rate = (values[index + step] - values[index]) / dt
        if abs(rate) > abs(best_value):
            best_value = rate
            best_time = times[index]
    return {"value": best_value, "time_s": best_time}


def _peak_frequency(times: list[float], values: list[float]) -> dict[str, float]:
    peaks: list[tuple[float, float]] = []
    for index in range(1, len(values) - 1):
        if values[index] >= values[index - 1] and values[index] > values[index + 1]:
            peaks.append((times[index], abs(values[index])))
    if len(peaks) < 2:
        return {"oscillation_frequency_hz": 0.0, "damping_ratio_estimate": 0.0}
    periods = [peaks[index + 1][0] - peaks[index][0] for index in range(len(peaks) - 1) if peaks[index + 1][0] > peaks[index][0]]
    avg_period = sum(periods) / len(periods) if periods else 0.0
    frequency = 1.0 / avg_period if avg_period > 0 else 0.0
    decrements: list[float] = []
    for index in range(len(peaks) - 1):
        a = peaks[index][1]
        b = peaks[index + 1][1]
        if a > 1e-12 and b > 1e-12:
            decrements.append(math.log(a / b))
    avg_dec = sum(decrements) / len(decrements) if decrements else 0.0
    damping = avg_dec / (2.0 * math.pi) if avg_dec > 0 else 0.0
    return {"oscillation_frequency_hz": frequency, "damping_ratio_estimate": damping}


def _values_for_kind(values: list[float], kind: str, base_frequency_hz: float) -> list[float]:
    if kind == "frequency":
        return [value / base_frequency_hz for value in values]
    return values


def analyze_transient_stability_trace(
    trace: dict[str, list[float]],
    *,
    kind: str,
    base_frequency_hz: float,
    analysis_window: list[float] | tuple[float, float] | None,
    prefault_window: list[float] | tuple[float, float] | None,
    postfault_window: list[float] | tuple[float, float] | None,
    settling_threshold_pu: float,
    max_speed_deviation_pu: float,
    rocof_window_samples: int,
    voltage_low_limit_pu: float,
    voltage_recovery_limit_pu: float,
    assess_voltage_channels: bool,
    min_samples: int,
) -> dict[str, Any]:
    raw_x = trace["x"]
    raw_y = _values_for_kind(trace["y"], kind, base_frequency_hz)
    _validate_time_axis(raw_x)

    win_x, win_y = _window_values(raw_x, raw_y, analysis_window, default_start=raw_x[0], default_end=raw_x[-1])
    if len(win_x) < min_samples:
        raise ValueError(f"Not enough samples in analysis window: {len(win_x)} < {min_samples}")

    default_prefault = _default_short_window(win_x, at_start=True)
    default_postfault = _default_short_window(win_x, at_start=False)
    _, prefault_values = _window_values(win_x, win_y, prefault_window, default_start=default_prefault[0], default_end=default_prefault[1])
    _, postfault_values = _window_values(win_x, win_y, postfault_window, default_start=default_postfault[0], default_end=default_postfault[1])
    if not prefault_values or not postfault_values:
        raise ValueError("Prefault or postfault window contains no data")

    initial = _mean(prefault_values)
    steady = _mean(postfault_values)
    deviations = [value - initial for value in win_y]
    abs_deviations = [abs(value) for value in deviations]
    max_abs_deviation = max(abs_deviations)
    max_index = abs_deviations.index(max_abs_deviation)
    rate = _max_rate(win_x, win_y, rocof_window_samples)
    oscillation = _peak_frequency(win_x, deviations)
    settling = _settling_time(win_x, win_y, steady, settling_threshold_pu)

    base_metrics = {
        "sample_count": len(win_x),
        "t_start": win_x[0],
        "t_end": win_x[-1],
        "initial_value": initial,
        "min_value": min(win_y),
        "max_value": max(win_y),
        "steady_value": steady,
        "steady_deviation": steady - initial,
        "rms": _rms(win_y),
        "max_abs_deviation": max_abs_deviation,
        "max_abs_deviation_time_s": win_x[max_index],
        "max_rate": rate["value"],
        "max_rate_time_s": rate["time_s"],
        "settling_time_s": settling,
        "settled_within_threshold": settling is not None,
        **oscillation,
    }

    if kind in {"speed_pu", "frequency"}:
        is_stable = max_abs_deviation <= max_speed_deviation_pu and settling is not None
        base_metrics.update(
            {
                "assessment_type": "rotor_speed",
                "max_speed_deviation_pu": max_abs_deviation,
                "max_rocof_hz_per_s": rate["value"] * base_frequency_hz,
                "is_stable": is_stable,
                "criterion": f"max speed deviation <= {max_speed_deviation_pu} pu and settled",
            }
        )
    elif kind == "voltage_pu" or (kind == "voltage" and assess_voltage_channels):
        min_voltage = min(win_y)
        recovered = steady >= voltage_recovery_limit_pu
        is_stable = min_voltage >= voltage_low_limit_pu and recovered
        base_metrics.update(
            {
                "assessment_type": "voltage_recovery",
                "min_voltage_pu": min_voltage,
                "recovered_above_limit": recovered,
                "is_stable": is_stable,
                "criterion": f"min voltage >= {voltage_low_limit_pu} pu and steady >= {voltage_recovery_limit_pu} pu",
            }
        )
    elif kind == "voltage":
        base_metrics.update(
            {
                "assessment_type": "supporting_voltage_waveform",
                "is_stable": None,
                "criterion": "instantaneous voltage waveform; set voltage_pu or assess_voltage_channels=true for pu recovery criterion",
            }
        )
    else:
        base_metrics.update(
            {
                "assessment_type": "supporting_waveform",
                "is_stable": None,
                "criterion": "supporting metric only",
            }
        )
    return base_metrics


def _report_assessment(summary: dict[str, Any]) -> str:
    if summary["unstable_channel_count"] > 0:
        return "attention_required"
    if summary["assessed_channel_count"] == 0:
        return "insufficient_assessed_channels"
    return "stable_by_configured_criteria"


def _format_optional(value: float | None, unit: str = "") -> str:
    if value is None:
        return "not assessed"
    suffix = f" {unit}" if unit else ""
    return f"{value:.6f}{suffix}"


def _write_artifacts(result_data: dict[str, Any], output_dir: Path, prefix: str, *, generate_report: bool) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / f"{prefix}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "kind",
                "plot_index",
                "channel",
                "assessment_type",
                "is_stable",
                "sample_count",
                "initial_value",
                "min_value",
                "max_value",
                "steady_value",
                "max_abs_deviation",
                "max_rate",
                "settling_time_s",
            ]
        )
        for row in result_data["channels"]:
            analysis = row["analysis"]
            writer.writerow(
                [
                    row["kind"],
                    row["plot_index"],
                    row["channel"],
                    analysis["assessment_type"],
                    analysis["is_stable"],
                    analysis["sample_count"],
                    f"{analysis['initial_value']:.9g}",
                    f"{analysis['min_value']:.9g}",
                    f"{analysis['max_value']:.9g}",
                    f"{analysis['steady_value']:.9g}",
                    f"{analysis['max_abs_deviation']:.9g}",
                    f"{analysis['max_rate']:.9g}",
                    "" if analysis["settling_time_s"] is None else f"{analysis['settling_time_s']:.9g}",
                ]
            )

    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        lines = [
            f"# {result_data['report']['title']}",
            "",
            "## Executive Summary",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Job ID: `{result_data['job_id']}`",
            f"- Overall assessment: `{result_data['summary']['overall_assessment']}`",
            f"- Assessed channels: `{result_data['summary']['assessed_channel_count']}`",
            f"- Unstable channels: `{result_data['summary']['unstable_channel_count']}`",
            f"- Max speed deviation: `{result_data['summary']['max_speed_deviation_pu']:.6f} pu`",
            f"- Max RoCoF: `{result_data['summary']['max_rocof_hz_per_s']:.6f} Hz/s`",
            f"- Minimum pu/RMS voltage: `{_format_optional(result_data['summary']['min_voltage_pu'], 'pu')}`",
            "",
            "## Key Metrics",
            "",
            "| kind | channel | assessment | stable | initial | min | max | steady | max deviation | settling s |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in result_data["channels"]:
            analysis = row["analysis"]
            settling = "" if analysis["settling_time_s"] is None else f"{analysis['settling_time_s']:.6f}"
            stable = "" if analysis["is_stable"] is None else str(analysis["is_stable"])
            lines.append(
                f"| {row['kind']} | `{row['channel']}` | {analysis['assessment_type']} | {stable} | "
                f"{analysis['initial_value']:.6f} | {analysis['min_value']:.6f} | "
                f"{analysis['max_value']:.6f} | {analysis['steady_value']:.6f} | "
                f"{analysis['max_abs_deviation']:.6f} | {settling} |"
            )
        lines.extend(
            [
                "",
                "## Engineering Notes",
                "",
                "- This report is generated from a real CloudPSS EMT run and the configured output channels.",
                "- The stability conclusion is a lightweight waveform-screening result, not a replacement for a full transient stability study.",
                "- Review channel units, fault scenario setup, protection actions, and model-specific criteria before using the conclusion for engineering sign-off.",
                "",
                "## Recommended Next Steps",
                "",
            ]
        )
        if result_data["summary"]["overall_assessment"] == "attention_required":
            lines.extend(
                [
                    "- Inspect unstable or marginal channels and verify whether the disturbance scenario is configured as intended.",
                    "- Run a fault clearing scan or targeted stability margin study around the observed event window.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Confirm the monitored channels cover all critical generators and buses.",
                    "- Add explicit fault scenario metadata when converting this screening report into a formal study record.",
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


def run_transient_stability_report(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None, timeout: int = 300) -> dict[str, Any]:
    resolved = _resolve_config(config)
    job = run_emt(model, timeout=timeout)
    selected = _select_traces(job.result, resolved["channels"], resolved["auto_max_channels"])

    rows: list[dict[str, Any]] = []
    for item in selected:
        analysis = analyze_transient_stability_trace(
            item["trace"],
            kind=item["kind"],
            base_frequency_hz=resolved["base_frequency_hz"],
            analysis_window=resolved["analysis_window"],
            prefault_window=resolved["prefault_window"],
            postfault_window=resolved["postfault_window"],
            settling_threshold_pu=resolved["settling_threshold_pu"],
            max_speed_deviation_pu=resolved["max_speed_deviation_pu"],
            rocof_window_samples=resolved["rocof_window_samples"],
            voltage_low_limit_pu=resolved["voltage_low_limit_pu"],
            voltage_recovery_limit_pu=resolved["voltage_recovery_limit_pu"],
            assess_voltage_channels=resolved["assess_voltage_channels"],
            min_samples=resolved["min_samples"],
        )
        rows.append(
            {
                "kind": item["kind"],
                "plot_index": item["plot_index"],
                "plot": item["plot"],
                "channel": item["channel"],
                "analysis": analysis,
            }
        )

    assessed = [row for row in rows if row["analysis"]["is_stable"] is not None]
    unstable = [row for row in assessed if row["analysis"]["is_stable"] is False]
    speed_rows = [row for row in rows if row["kind"] in {"speed_pu", "frequency"}]
    voltage_rows = [row for row in rows if row["analysis"].get("assessment_type") == "voltage_recovery"]
    max_speed_deviation = max((row["analysis"].get("max_speed_deviation_pu", 0.0) for row in speed_rows), default=0.0)
    max_rocof = max((abs(row["analysis"].get("max_rocof_hz_per_s", 0.0)) for row in speed_rows), default=0.0)
    min_voltage = min((row["analysis"].get("min_voltage_pu", 1.0) for row in voltage_rows), default=None)

    summary = {
        "channel_count": len(rows),
        "assessed_channel_count": len(assessed),
        "unstable_channel_count": len(unstable),
        "max_speed_deviation_pu": max_speed_deviation,
        "max_rocof_hz_per_s": max_rocof,
        "min_voltage_pu": min_voltage,
    }
    summary["overall_assessment"] = _report_assessment(summary)

    report = resolved["report"]
    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "job_id": getattr(job, "id", None),
        "report": {
            "title": report.get("title", "Transient Stability Screening Report"),
            "scenario": report.get("scenario", "existing EMT scenario"),
            "author": report.get("author", "CloudPSS agent skill"),
        },
        "assessment": {
            "base_frequency_hz": resolved["base_frequency_hz"],
            "analysis_window": resolved["analysis_window"],
            "prefault_window": resolved["prefault_window"],
            "postfault_window": resolved["postfault_window"],
            "settling_threshold_pu": resolved["settling_threshold_pu"],
            "max_speed_deviation_pu": resolved["max_speed_deviation_pu"],
            "voltage_low_limit_pu": resolved["voltage_low_limit_pu"],
            "voltage_recovery_limit_pu": resolved["voltage_recovery_limit_pu"],
            "assess_voltage_channels": resolved["assess_voltage_channels"],
            "min_samples": resolved["min_samples"],
        },
        "summary": summary,
        "channels": rows,
    }

    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "transient_stability_report")
    artifacts = _write_artifacts(
        result_data,
        target_dir,
        prefix,
        generate_report=bool(output_config.get("generate_report", True)),
    )
    return {**result_data, "artifacts": artifacts}
