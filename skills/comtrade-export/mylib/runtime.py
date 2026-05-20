from __future__ import annotations

import math
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


def choose_plot_channels(result, *, plot_index: int = 0, max_channels: int = 3) -> dict[str, Any]:
    plots = list(result.getPlots())
    if not plots:
        raise RuntimeError("No plots in EMT result")
    if plot_index >= len(plots):
        raise IndexError(f"plot_index {plot_index} out of range")
    channel_names = list(result.getPlotChannelNames(plot_index))[:max_channels]
    channels: dict[str, dict[str, list[float]]] = {}
    for channel_name in channel_names:
        data = result.getPlotChannelData(plot_index, channel_name)
        if not data:
            continue
        x_values = [float(value) for value in data.get("x", [])]
        y_values = [float(value) for value in data.get("y", [])]
        if len(x_values) > 1 and len(x_values) == len(y_values):
            channels[channel_name] = {"x": x_values, "y": y_values}
    if not channels:
        raise RuntimeError("No channel data selected for COMTRADE export")
    sample_count = min(len(data["x"]) for data in channels.values())
    if sample_count < 2:
        raise RuntimeError("Not enough samples for COMTRADE export")
    for data in channels.values():
        data["x"] = data["x"][:sample_count]
        data["y"] = data["y"][:sample_count]
    return {
        "plot_index": plot_index,
        "plot": plots[plot_index].get("key") or plots[plot_index].get("name") or f"plot_{plot_index}",
        "channels": channels,
        "sample_count": sample_count,
    }


def _guess_unit(channel_name: str) -> str:
    lower = channel_name.lower()
    if "vac" in lower or "volt" in lower or "_v" in lower:
        return "kV"
    if "#p" in lower or "power" in lower:
        return "MW"
    if "#q" in lower:
        return "Mvar"
    if "wr" in lower or "freq" in lower:
        return "pu"
    return "pu"


def _guess_phase(channel_name: str) -> str:
    if channel_name.endswith(":1"):
        return "B"
    if channel_name.endswith(":2"):
        return "C"
    return "A"


def _safe_channel_id(channel_name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in channel_name)
    return cleaned[-64:] or "channel"


def _sampling_rate(x_values: list[float]) -> float:
    if len(x_values) < 2:
        return 1.0
    dt = x_values[1] - x_values[0]
    if dt <= 0:
        return 1.0
    return 1.0 / dt


def _scale_channel(y_values: list[float]) -> tuple[float, float, list[int]]:
    y_min = min(y_values)
    y_max = max(y_values)
    if math.isclose(y_min, y_max):
        return 1.0, y_min, [0 for _ in y_values]
    a = (y_max - y_min) / 65534.0
    b = (y_max + y_min) / 2.0
    integers = []
    for value in y_values:
        raw = int(round((value - b) / a))
        integers.append(max(-32767, min(32767, raw)))
    return a, b, integers


def export_result_to_comtrade(result, output_dir: Path, *, filename: str = "cloudpss_emt", plot_index: int = 0, max_channels: int = 3) -> dict[str, Any]:
    selected = choose_plot_channels(result, plot_index=plot_index, max_channels=max_channels)
    channels = selected["channels"]
    sample_count = selected["sample_count"]
    first_channel = next(iter(channels.values()))
    x_values = first_channel["x"]
    rate = _sampling_rate(x_values)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = output_dir / f"{filename}.cfg"
    dat_path = output_dir / f"{filename}.dat"

    channel_infos: list[dict[str, Any]] = []
    scaled_values: dict[str, list[int]] = {}
    for index, (channel_name, channel_data) in enumerate(channels.items(), start=1):
        a, b, integers = _scale_channel(channel_data["y"])
        channel_id = _safe_channel_id(channel_name)
        channel_infos.append(
            {
                "index": index,
                "source_name": channel_name,
                "channel_id": channel_id,
                "phase": _guess_phase(channel_name),
                "unit": _guess_unit(channel_name),
                "a": a,
                "b": b,
                "min": -32767,
                "max": 32767,
            }
        )
        scaled_values[channel_name] = integers

    cfg_lines = [
        "CloudPSS,EMT,1999",
        f"{len(channel_infos)},{len(channel_infos)}A,0D",
    ]
    for info in channel_infos:
        cfg_lines.append(
            f"{info['index']},{info['channel_id']},{info['phase']},{info['channel_id']},{info['unit']},"
            f"{info['a']:.12g},{info['b']:.12g},0,{info['min']},{info['max']},1,1,p"
        )
    cfg_lines.extend(
        [
            "50.000000",
            "1",
            f"{rate:.6f},{sample_count}",
            "19/05/2026,00:00:00.000",
            "19/05/2026,00:00:00.000",
            "ASCII",
            "1.000000",
        ]
    )
    cfg_path.write_text("\n".join(cfg_lines), encoding="utf-8")

    dat_lines: list[str] = []
    channel_names = list(channels.keys())
    for sample_index in range(sample_count):
        timestamp_us = int(round(x_values[sample_index] * 1_000_000))
        values = [str(scaled_values[channel_name][sample_index]) for channel_name in channel_names]
        dat_lines.append(f"{sample_index + 1},{timestamp_us}," + ",".join(values))
    dat_path.write_text("\n".join(dat_lines), encoding="utf-8")

    validation = validate_ascii_comtrade(cfg_path, dat_path, expected_channels=len(channel_infos), expected_samples=sample_count)
    return {
        "plot_index": selected["plot_index"],
        "plot": selected["plot"],
        "cfg_path": str(cfg_path),
        "dat_path": str(dat_path),
        "channel_count": len(channel_infos),
        "sample_count": sample_count,
        "sampling_rate_hz": rate,
        "channels": channel_infos,
        "validation": validation,
    }


def validate_ascii_comtrade(cfg_path: Path, dat_path: Path, *, expected_channels: int, expected_samples: int) -> dict[str, Any]:
    cfg_lines = cfg_path.read_text(encoding="utf-8").splitlines()
    if len(cfg_lines) < expected_channels + 8:
        raise RuntimeError("CFG file is too short")
    second_line = cfg_lines[1].split(",")
    analog_count = int(second_line[1].rstrip("A"))
    if analog_count != expected_channels:
        raise RuntimeError(f"CFG analog channel count mismatch: {analog_count} != {expected_channels}")
    dat_lines = [line for line in dat_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(dat_lines) != expected_samples:
        raise RuntimeError(f"DAT sample count mismatch: {len(dat_lines)} != {expected_samples}")
    expected_fields = 2 + expected_channels
    for line in dat_lines[:10]:
        if len(line.split(",")) != expected_fields:
            raise RuntimeError(f"DAT row field count mismatch: {line}")
    return {"cfg_lines": len(cfg_lines), "dat_rows": len(dat_lines), "analog_channels": analog_count}


def run_emt_and_export_comtrade(model, output_dir: Path, *, timeout: int = 300) -> dict[str, Any]:
    job = run_emt(model, timeout=timeout)
    export = export_result_to_comtrade(job.result, output_dir, filename=f"comtrade_{getattr(job, 'id', 'job')}", plot_index=0, max_channels=3)
    return {
        "job_id": getattr(job, "id", None),
        "status": 1,
        "export": export,
    }
