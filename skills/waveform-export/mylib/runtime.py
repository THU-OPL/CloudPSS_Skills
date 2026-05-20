from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import time
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/<your-account>/IEEE3")


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
    token = env_values.get("SIMSTUDIO_TOKEN") or env_values.get("CLOUDPSS_TOKEN")
    if token:
        api_url = env_values.get("CLOUDPSS_API_URL")
        if api_url and not os.environ.get("CLOUDPSS_API_URL"):
            os.environ["CLOUDPSS_API_URL"] = api_url
        return token
    path = Path(token_path)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Missing token file: {path}")


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


def extract_waveforms(result, *, max_plots: int | None = None, max_channels_per_plot: int | None = None, time_range: tuple[float | None, float | None] | None = None) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    plots = list(result.getPlots())
    for plot_index, plot in enumerate(plots):
        if max_plots is not None and plot_index >= max_plots:
            break
        channel_names = list(result.getPlotChannelNames(plot_index))
        if max_channels_per_plot is not None:
            channel_names = channel_names[:max_channels_per_plot]
        channels: dict[str, dict[str, list[Any]]] = {}
        for channel_name in channel_names:
            data = result.getPlotChannelData(plot_index, channel_name)
            if not data:
                continue
            x_values = list(data.get("x", []))
            y_values = list(data.get("y", []))
            if time_range:
                start, end = time_range
                filtered_x: list[Any] = []
                filtered_y: list[Any] = []
                for x_value, y_value in zip(x_values, y_values):
                    if start is not None and x_value < start:
                        continue
                    if end is not None and x_value > end:
                        continue
                    filtered_x.append(x_value)
                    filtered_y.append(y_value)
                x_values, y_values = filtered_x, filtered_y
            if x_values and y_values:
                channels[channel_name] = {"x": x_values, "y": y_values}
        if channels:
            exported.append({"plot_index": plot_index, "plot": _plot_name(plot, plot_index), "channels": channels})
    if not exported:
        raise RuntimeError("No waveform channels extracted")
    return exported


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name).strip("_") or "channel"


def _channel_stats(channel_data: dict[str, list[Any]]) -> dict[str, Any]:
    x_values = channel_data["x"]
    y_values = channel_data["y"]
    if len(x_values) != len(y_values):
        raise RuntimeError("Waveform x/y length mismatch")
    if len(x_values) < 2:
        raise RuntimeError("Waveform has fewer than 2 samples")
    if any(float(x_values[i]) > float(x_values[i + 1]) for i in range(len(x_values) - 1)):
        raise RuntimeError("Waveform time axis is not monotonic")
    numeric_y = [float(value) for value in y_values]
    return {
        "sample_count": len(x_values),
        "t_start": float(x_values[0]),
        "t_end": float(x_values[-1]),
        "value_min": min(numeric_y),
        "value_max": max(numeric_y),
    }


def export_waveforms(waveforms: list[dict[str, Any]], output_dir: Path, *, prefix: str = "waveform") -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{prefix}.json"
    json_path.write_text(json.dumps({"plots": waveforms}, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_paths: list[str] = []
    stats: dict[str, Any] = {}
    for plot in waveforms:
        for channel_name, channel_data in plot["channels"].items():
            key = f"plot_{plot['plot_index']}:{channel_name}"
            stats[key] = _channel_stats(channel_data)
            csv_path = output_dir / f"{prefix}_plot_{plot['plot_index']}_{_safe_name(channel_name)}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as output_file:
                writer = csv.writer(output_file)
                writer.writerow(["time", "value"])
                for x_value, y_value in zip(channel_data["x"], channel_data["y"]):
                    writer.writerow([x_value, y_value])
            csv_paths.append(str(csv_path))

    if not stats:
        raise RuntimeError("No waveform stats generated")
    return {
        "json_path": str(json_path),
        "csv_paths": csv_paths,
        "channel_stats": stats,
        "exported_channel_count": len(stats),
    }


def run_emt_and_export_waveforms(model, output_dir: Path, *, max_plots: int = 2, max_channels_per_plot: int = 2, timeout: int = 300) -> dict[str, Any]:
    job = run_emt(model, timeout=timeout)
    waveforms = extract_waveforms(job.result, max_plots=max_plots, max_channels_per_plot=max_channels_per_plot)
    export = export_waveforms(waveforms, output_dir, prefix=f"waveforms_{getattr(job, 'id', 'job')}")
    return {
        "job_id": getattr(job, "id", None),
        "status": 1,
        "plot_count": len(list(job.result.getPlots())),
        "export": export,
    }
