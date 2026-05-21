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


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/<your-account>/IEEE3")
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "harmonic-analysis"


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
        raise ValueError(
            "Set CLOUDPSS_TEST_EMT_MODEL_RID or pass a model RID under your own account. "
            "If needed, save or build an EMT-ready copy from model/CloudPSS/IEEE3 first."
        )
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
        "fundamental_freq": float(analysis.get("fundamental_freq", 50.0)),
        "max_harmonic": int(analysis.get("max_harmonic", 25)),
        "thd_limit_percent": float(analysis.get("thd_limit_percent", analysis.get("thd_limit", 5.0))),
        "analysis_window": analysis.get("analysis_window"),
        "min_samples": int(analysis.get("min_samples", 128)),
        "auto_max_channels": int(channels.get("auto_max_channels", 3)),
        "channels": {
            "voltage": list(channels.get("voltage", [])),
            "current": list(channels.get("current", [])),
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


def _auto_select_traces(result, max_channels: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for plot_index, plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            data = result.getPlotChannelData(plot_index, channel_name)
            if not data:
                continue
            x_values = [float(value) for value in data.get("x", [])]
            y_values = [float(value) for value in data.get("y", [])]
            if len(x_values) > 1 and len(x_values) == len(y_values):
                selected.append(
                    {
                        "kind": "generic",
                        "channel": channel_name,
                        "plot_index": plot_index,
                        "plot": _plot_name(plot, plot_index),
                        "trace": {"x": x_values, "y": y_values},
                    }
                )
            if len(selected) >= max_channels:
                return selected
    if not selected:
        raise RuntimeError("No channel data available for harmonic analysis")
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


def _window_trace(trace: dict[str, list[float]], analysis_window: list[float] | tuple[float, float] | None) -> dict[str, list[float]]:
    x_values = trace["x"]
    y_values = trace["y"]
    if not analysis_window:
        end = x_values[-1]
        start = max(x_values[0], end - min(1.0, max((end - x_values[0]) / 5.0, 0.02)))
    else:
        if len(analysis_window) != 2:
            raise ValueError("analysis_window must be [start, end]")
        start = float(analysis_window[0])
        end = float(analysis_window[1])
    window_x: list[float] = []
    window_y: list[float] = []
    for x_value, y_value in zip(x_values, y_values):
        if start <= x_value <= end:
            window_x.append(x_value)
            window_y.append(y_value)
    return {"x": window_x, "y": window_y}


def _sampling_rate(x_values: list[float]) -> float:
    intervals = [x_values[index + 1] - x_values[index] for index in range(len(x_values) - 1)]
    if any(interval <= 0 for interval in intervals):
        raise ValueError("Waveform time axis is not strictly increasing")
    return 1.0 / (sum(intervals) / len(intervals))


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


def _frequency_amplitude(x_values: list[float], y_values: list[float], frequency_hz: float) -> float:
    if frequency_hz <= 0:
        return 0.0
    origin = x_values[0]
    n_samples = len(y_values)
    cos_sum = 0.0
    sin_sum = 0.0
    for x_value, y_value in zip(x_values, y_values):
        angle = 2.0 * math.pi * frequency_hz * (x_value - origin)
        cos_sum += y_value * math.cos(angle)
        sin_sum += y_value * math.sin(angle)
    return 2.0 * math.sqrt(cos_sum * cos_sum + sin_sum * sin_sum) / n_samples


def analyze_trace(
    trace: dict[str, list[float]],
    *,
    fundamental_freq: float,
    max_harmonic: int,
    analysis_window: list[float] | tuple[float, float] | None,
    min_samples: int,
) -> dict[str, Any]:
    windowed = _window_trace(trace, analysis_window)
    x_values = windowed["x"]
    y_values = windowed["y"]
    if len(x_values) < min_samples:
        raise ValueError(f"Not enough samples in analysis window: {len(x_values)} < {min_samples}")

    sample_rate = _sampling_rate(x_values)
    nyquist = sample_rate / 2.0
    dc_component = sum(y_values) / len(y_values)
    ac_values = [value - dc_component for value in y_values]
    fundamental_amp = _frequency_amplitude(x_values, ac_values, fundamental_freq)
    fundamental_rms = fundamental_amp / math.sqrt(2.0)

    harmonics: dict[str, Any] = {}
    harmonic_rms_square = 0.0
    for order in range(2, max_harmonic + 1):
        frequency = fundamental_freq * order
        if frequency > nyquist:
            break
        amplitude = _frequency_amplitude(x_values, ac_values, frequency)
        harmonic_rms = amplitude / math.sqrt(2.0)
        harmonic_rms_square += harmonic_rms * harmonic_rms
        content_percent = (amplitude / fundamental_amp * 100.0) if fundamental_amp > 1e-12 else 0.0
        harmonics[str(order)] = {
            "frequency_hz": frequency,
            "amplitude": amplitude,
            "rms": harmonic_rms,
            "content_percent": content_percent,
        }

    thd_percent = (math.sqrt(harmonic_rms_square) / fundamental_rms * 100.0) if fundamental_rms > 1e-12 else 0.0
    return {
        "sample_count": len(x_values),
        "t_start": x_values[0],
        "t_end": x_values[-1],
        "sampling_rate_hz": sample_rate,
        "nyquist_hz": nyquist,
        "dc_component": dc_component,
        "rms": _rms(y_values),
        "fundamental": {
            "frequency_hz": fundamental_freq,
            "amplitude": fundamental_amp,
            "rms": fundamental_rms,
        },
        "harmonics": harmonics,
        "thd_percent": thd_percent,
    }


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name).strip("_") or "channel"


def _write_artifacts(result_data: dict[str, Any], output_dir: Path, prefix: str, *, generate_report: bool, export_spectrum: bool) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / f"{prefix}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["kind", "plot_index", "channel", "sample_count", "fundamental_amp", "fundamental_rms", "rms", "thd_percent"])
        for row in result_data["channels"]:
            writer.writerow(
                [
                    row["kind"],
                    row["plot_index"],
                    row["channel"],
                    row["analysis"]["sample_count"],
                    f"{row['analysis']['fundamental']['amplitude']:.9g}",
                    f"{row['analysis']['fundamental']['rms']:.9g}",
                    f"{row['analysis']['rms']:.9g}",
                    f"{row['analysis']['thd_percent']:.6f}",
                ]
            )

    spectrum_path = output_dir / f"{prefix}_spectrum_{timestamp}.csv"
    if export_spectrum:
        with spectrum_path.open("w", newline="", encoding="utf-8") as spectrum_file:
            writer = csv.writer(spectrum_file)
            writer.writerow(["kind", "channel", "harmonic_order", "frequency_hz", "amplitude", "rms", "content_percent"])
            for row in result_data["channels"]:
                for order, harmonic in row["analysis"]["harmonics"].items():
                    writer.writerow(
                        [
                            row["kind"],
                            row["channel"],
                            order,
                            f"{harmonic['frequency_hz']:.6f}",
                            f"{harmonic['amplitude']:.9g}",
                            f"{harmonic['rms']:.9g}",
                            f"{harmonic['content_percent']:.6f}",
                        ]
                    )
    else:
        spectrum_path = Path("")

    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        lines = [
            "# Harmonic Analysis Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Job ID: `{result_data['job_id']}`",
            f"- Fundamental: `{result_data['analysis']['fundamental_freq']} Hz`",
            f"- THD limit: `{result_data['analysis']['thd_limit_percent']}%`",
            f"- Max THD: `{result_data['summary']['max_thd_percent']:.6f}%`",
            f"- Pass THD limit: `{result_data['summary']['pass_thd_limit']}`",
            "",
            "| kind | channel | samples | fundamental_rms | rms | THD % |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for row in result_data["channels"]:
            analysis = row["analysis"]
            lines.append(
                f"| {row['kind']} | `{row['channel']}` | {analysis['sample_count']} | "
                f"{analysis['fundamental']['rms']:.6f} | {analysis['rms']:.6f} | {analysis['thd_percent']:.6f} |"
            )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = Path("")

    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "spectrum_csv_path": str(spectrum_path) if spectrum_path else "",
        "markdown_path": str(markdown_path) if markdown_path else "",
    }


def run_harmonic_analysis(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None, timeout: int = 300) -> dict[str, Any]:
    resolved = _resolve_config(config)
    job = run_emt(model, timeout=timeout)
    selected = _select_traces(job.result, resolved["channels"], resolved["auto_max_channels"])

    rows: list[dict[str, Any]] = []
    for item in selected:
        analysis = analyze_trace(
            item["trace"],
            fundamental_freq=resolved["fundamental_freq"],
            max_harmonic=resolved["max_harmonic"],
            analysis_window=resolved["analysis_window"],
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

    max_thd = max(row["analysis"]["thd_percent"] for row in rows)
    thd_limit = resolved["thd_limit_percent"]
    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "job_id": getattr(job, "id", None),
        "analysis": {
            "fundamental_freq": resolved["fundamental_freq"],
            "max_harmonic": resolved["max_harmonic"],
            "thd_limit_percent": thd_limit,
            "analysis_window": resolved["analysis_window"],
            "min_samples": resolved["min_samples"],
        },
        "summary": {
            "channel_count": len(rows),
            "max_thd_percent": max_thd,
            "thd_violations": sum(1 for row in rows if row["analysis"]["thd_percent"] > thd_limit),
            "pass_thd_limit": all(row["analysis"]["thd_percent"] <= thd_limit for row in rows),
        },
        "channels": rows,
    }

    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "harmonic_analysis")
    artifacts = _write_artifacts(
        result_data,
        target_dir,
        prefix,
        generate_report=bool(output_config.get("generate_report", True)),
        export_spectrum=bool(output_config.get("export_spectrum", True)),
    )
    return {**result_data, "artifacts": artifacts}
