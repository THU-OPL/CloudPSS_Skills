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
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "frequency-response-analysis"


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
    analysis = config.get("analysis", {})
    channels = config.get("channels", {})
    output = config.get("output", {})
    return {
        "base_frequency_hz": float(analysis.get("base_frequency_hz", analysis.get("base_frequency", 50.0))),
        "analysis_window": analysis.get("analysis_window"),
        "initial_window": analysis.get("initial_window"),
        "steady_window": analysis.get("steady_window"),
        "settling_threshold_hz": float(analysis.get("settling_threshold_hz", analysis.get("settling_threshold", 0.05))),
        "rocof_window_samples": max(1, int(analysis.get("rocof_window_samples", 5))),
        "min_samples": int(analysis.get("min_samples", 128)),
        "auto_max_channels": int(channels.get("auto_max_channels", 3)),
        "channels": {
            "frequency": list(channels.get("frequency", [])),
            "speed_pu": list(channels.get("speed_pu", [])),
            "generic": list(channels.get("generic", [])),
        },
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


def _looks_like_frequency_channel(channel_name: str) -> bool:
    lower = channel_name.lower()
    return "wr" in lower or "freq" in lower or "speed" in lower


def _auto_select_traces(result, max_channels: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for plot_index, plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            if not _looks_like_frequency_channel(channel_name):
                continue
            data = result.getPlotChannelData(plot_index, channel_name)
            if not data:
                continue
            x_values = [float(value) for value in data.get("x", [])]
            y_values = [float(value) for value in data.get("y", [])]
            if len(x_values) > 1 and len(x_values) == len(y_values):
                selected.append(
                    {
                        "kind": "speed_pu",
                        "channel": channel_name,
                        "plot_index": plot_index,
                        "plot": _plot_name(plot, plot_index),
                        "trace": {"x": x_values, "y": y_values},
                    }
                )
            if len(selected) >= max_channels:
                return selected
    if not selected:
        raise RuntimeError("No frequency or speed channel data available")
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


def _time_window_values(
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


def _to_frequency_hz(values: list[float], kind: str, base_frequency_hz: float) -> list[float]:
    if kind == "frequency":
        return values
    return [value * base_frequency_hz for value in values]


def _max_rocof(times: list[float], values: list[float], window_samples: int) -> dict[str, float]:
    if len(times) < 2:
        return {"max_rocof_hz_per_s": 0.0, "max_rocof_time_s": times[0] if times else 0.0}
    best_value = 0.0
    best_time = times[0]
    step = max(1, window_samples)
    for index in range(0, len(times) - step):
        dt = times[index + step] - times[index]
        if dt <= 0:
            continue
        rocof = (values[index + step] - values[index]) / dt
        if abs(rocof) > abs(best_value):
            best_value = rocof
            best_time = times[index]
    return {"max_rocof_hz_per_s": best_value, "max_rocof_time_s": best_time}


def _settling_time(times: list[float], values: list[float], steady_value: float, threshold_hz: float) -> float | None:
    for index, current_time in enumerate(times):
        tail = values[index:]
        if tail and all(abs(value - steady_value) <= threshold_hz for value in tail):
            return current_time
    return None


def analyze_frequency_trace(
    trace: dict[str, list[float]],
    *,
    kind: str,
    base_frequency_hz: float,
    analysis_window: list[float] | tuple[float, float] | None,
    initial_window: list[float] | tuple[float, float] | None,
    steady_window: list[float] | tuple[float, float] | None,
    settling_threshold_hz: float,
    rocof_window_samples: int,
    min_samples: int,
) -> dict[str, Any]:
    x_raw = trace["x"]
    y_hz_all = _to_frequency_hz(trace["y"], kind, base_frequency_hz)
    if any(x_raw[index] >= x_raw[index + 1] for index in range(len(x_raw) - 1)):
        raise ValueError("Waveform time axis is not strictly increasing")

    total_start = x_raw[0]
    total_end = x_raw[-1]
    win_x, win_y = _time_window_values(
        x_raw,
        y_hz_all,
        analysis_window,
        default_start=total_start,
        default_end=total_end,
    )
    if len(win_x) < min_samples:
        raise ValueError(f"Not enough samples in analysis window: {len(win_x)} < {min_samples}")

    duration = win_x[-1] - win_x[0]
    short_window = max(min(duration * 0.1, 0.5), 0.02)
    _, initial_values = _time_window_values(
        win_x,
        win_y,
        initial_window,
        default_start=win_x[0],
        default_end=min(win_x[-1], win_x[0] + short_window),
    )
    _, steady_values = _time_window_values(
        win_x,
        win_y,
        steady_window,
        default_start=max(win_x[0], win_x[-1] - short_window),
        default_end=win_x[-1],
    )

    initial_frequency = _mean(initial_values)
    steady_frequency = _mean(steady_values)
    min_frequency = min(win_y)
    max_frequency = max(win_y)
    min_index = win_y.index(min_frequency)
    max_index = win_y.index(max_frequency)
    deviations = [value - initial_frequency for value in win_y]
    max_abs_deviation = max(abs(value) for value in deviations)
    rocof = _max_rocof(win_x, win_y, rocof_window_samples)
    settling = _settling_time(win_x, win_y, steady_frequency, settling_threshold_hz)

    return {
        "sample_count": len(win_x),
        "t_start": win_x[0],
        "t_end": win_x[-1],
        "initial_frequency_hz": initial_frequency,
        "min_frequency_hz": min_frequency,
        "min_frequency_time_s": win_x[min_index],
        "max_frequency_hz": max_frequency,
        "max_frequency_time_s": win_x[max_index],
        "steady_frequency_hz": steady_frequency,
        "steady_deviation_hz": steady_frequency - initial_frequency,
        "max_abs_deviation_hz": max_abs_deviation,
        "max_rocof_hz_per_s": rocof["max_rocof_hz_per_s"],
        "max_rocof_time_s": rocof["max_rocof_time_s"],
        "settling_time_s": settling,
        "settled_within_threshold": settling is not None,
    }


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
                "sample_count",
                "initial_frequency_hz",
                "min_frequency_hz",
                "max_frequency_hz",
                "steady_frequency_hz",
                "max_abs_deviation_hz",
                "max_rocof_hz_per_s",
                "settling_time_s",
                "settled_within_threshold",
            ]
        )
        for row in result_data["channels"]:
            analysis = row["analysis"]
            writer.writerow(
                [
                    row["kind"],
                    row["plot_index"],
                    row["channel"],
                    analysis["sample_count"],
                    f"{analysis['initial_frequency_hz']:.9g}",
                    f"{analysis['min_frequency_hz']:.9g}",
                    f"{analysis['max_frequency_hz']:.9g}",
                    f"{analysis['steady_frequency_hz']:.9g}",
                    f"{analysis['max_abs_deviation_hz']:.9g}",
                    f"{analysis['max_rocof_hz_per_s']:.9g}",
                    "" if analysis["settling_time_s"] is None else f"{analysis['settling_time_s']:.9g}",
                    analysis["settled_within_threshold"],
                ]
            )

    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        lines = [
            "# Frequency Response Analysis Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Job ID: `{result_data['job_id']}`",
            f"- Base frequency: `{result_data['analysis']['base_frequency_hz']} Hz`",
            f"- Settling threshold: `{result_data['analysis']['settling_threshold_hz']} Hz`",
            f"- Max absolute deviation: `{result_data['summary']['max_abs_deviation_hz']:.6f} Hz`",
            f"- Max RoCoF: `{result_data['summary']['max_rocof_hz_per_s']:.6f} Hz/s`",
            f"- Pass settling threshold: `{result_data['summary']['pass_settling_threshold']}`",
            "",
            "| kind | channel | initial Hz | min Hz | max Hz | steady Hz | max deviation Hz | max RoCoF Hz/s | settling s |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in result_data["channels"]:
            analysis = row["analysis"]
            settling = "" if analysis["settling_time_s"] is None else f"{analysis['settling_time_s']:.6f}"
            lines.append(
                f"| {row['kind']} | `{row['channel']}` | {analysis['initial_frequency_hz']:.6f} | "
                f"{analysis['min_frequency_hz']:.6f} | {analysis['max_frequency_hz']:.6f} | "
                f"{analysis['steady_frequency_hz']:.6f} | {analysis['max_abs_deviation_hz']:.6f} | "
                f"{analysis['max_rocof_hz_per_s']:.6f} | {settling} |"
            )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = Path("")

    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "markdown_path": str(markdown_path) if markdown_path else "",
    }


def run_frequency_response_analysis(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None, timeout: int = 300) -> dict[str, Any]:
    resolved = _resolve_config(config)
    job = run_emt(model, timeout=timeout)
    selected = _select_traces(job.result, resolved["channels"], resolved["auto_max_channels"])

    rows: list[dict[str, Any]] = []
    for item in selected:
        analysis = analyze_frequency_trace(
            item["trace"],
            kind=item["kind"],
            base_frequency_hz=resolved["base_frequency_hz"],
            analysis_window=resolved["analysis_window"],
            initial_window=resolved["initial_window"],
            steady_window=resolved["steady_window"],
            settling_threshold_hz=resolved["settling_threshold_hz"],
            rocof_window_samples=resolved["rocof_window_samples"],
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

    if not rows:
        raise RuntimeError("No channels analyzed")

    max_abs_deviation = max(row["analysis"]["max_abs_deviation_hz"] for row in rows)
    max_rocof = max(abs(row["analysis"]["max_rocof_hz_per_s"]) for row in rows)
    pass_settling = all(row["analysis"]["settled_within_threshold"] for row in rows)
    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "job_id": getattr(job, "id", None),
        "analysis": {
            "base_frequency_hz": resolved["base_frequency_hz"],
            "analysis_window": resolved["analysis_window"],
            "initial_window": resolved["initial_window"],
            "steady_window": resolved["steady_window"],
            "settling_threshold_hz": resolved["settling_threshold_hz"],
            "rocof_window_samples": resolved["rocof_window_samples"],
            "min_samples": resolved["min_samples"],
        },
        "summary": {
            "channel_count": len(rows),
            "max_abs_deviation_hz": max_abs_deviation,
            "max_rocof_hz_per_s": max_rocof,
            "pass_settling_threshold": pass_settling,
        },
        "channels": rows,
    }

    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "frequency_response_analysis")
    artifacts = _write_artifacts(
        result_data,
        target_dir,
        prefix,
        generate_report=bool(output_config.get("generate_report", True)),
    )
    return {**result_data, "artifacts": artifacts}
