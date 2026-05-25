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
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "power-quality-analysis"


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


def _resolve_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    analysis = config.get("analysis", {})
    channels = config.get("channels", {})
    output = config.get("output", {})
    limits = analysis.get("limits", {})
    return {
        "fundamental_freq": float(analysis.get("fundamental_freq", 50.0)),
        "max_harmonic": int(analysis.get("max_harmonic", 25)),
        "analysis_window": analysis.get("analysis_window"),
        "event_window": analysis.get("event_window"),
        "reference_window": analysis.get("reference_window"),
        "cycle_samples": analysis.get("cycle_samples"),
        "min_samples": int(analysis.get("min_samples", 128)),
        "limits": {
            "thd_percent": float(limits.get("thd_percent", limits.get("thd", 5.0))),
            "single_harmonic_percent": float(limits.get("single_harmonic_percent", 3.0)),
            "voltage_dip_percent": float(limits.get("voltage_dip_percent", limits.get("voltage_dip", 10.0))),
            "voltage_swell_percent": float(limits.get("voltage_swell_percent", limits.get("voltage_swell", 10.0))),
            "unbalance_percent": float(limits.get("unbalance_percent", limits.get("unbalance", 2.0))),
            "dc_offset_percent": float(limits.get("dc_offset_percent", limits.get("dc_offset", 1.0))),
            "flicker_proxy_percent": float(limits.get("flicker_proxy_percent", 3.0)),
        },
        "auto_max_channels": int(channels.get("auto_max_channels", 3)),
        "channels": {
            "voltage": list(channels.get("voltage", [])),
            "current": list(channels.get("current", [])),
            "generic": list(channels.get("generic", [])),
        },
        "three_phase": list(channels.get("three_phase", [])),
        "output": output,
    }


def _plot_name(plot: dict[str, Any], index: int) -> str:
    return plot.get("key") or plot.get("name") or plot.get("title") or f"plot_{index}"


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


def _looks_like_voltage_channel(channel_name: str) -> bool:
    lower = channel_name.lower()
    if "wr" in lower or "freq" in lower or "theta" in lower:
        return False
    return lower.startswith("v") or "vac" in lower or "vrms" in lower or "voltage" in lower


def _auto_select_traces(result, max_channels: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for plot_index, plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            if not _looks_like_voltage_channel(channel_name):
                continue
            data = result.getPlotChannelData(plot_index, channel_name)
            if not data:
                continue
            x_values = [float(value) for value in data.get("x", [])]
            y_values = [float(value) for value in data.get("y", [])]
            if len(x_values) > 1 and len(x_values) == len(y_values):
                selected.append(
                    {
                        "kind": "voltage",
                        "channel": channel_name,
                        "plot_index": plot_index,
                        "plot": _plot_name(plot, plot_index),
                        "trace": {"x": x_values, "y": y_values},
                    }
                )
            if len(selected) >= max_channels:
                return selected
    if selected:
        return selected
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
        raise RuntimeError("No channel data available for power quality analysis")
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


def _default_analysis_window(x_values: list[float]) -> tuple[float, float]:
    end = x_values[-1]
    start = max(x_values[0], end - min(1.0, max((end - x_values[0]) / 5.0, 0.02)))
    return start, end


def _sampling_rate(x_values: list[float]) -> float:
    intervals = [x_values[index + 1] - x_values[index] for index in range(len(x_values) - 1)]
    if any(interval <= 0 for interval in intervals):
        raise ValueError("Waveform time axis is not strictly increasing")
    return 1.0 / (sum(intervals) / len(intervals))


def _rms(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot calculate RMS for empty values")
    return math.sqrt(sum(value * value for value in values) / len(values))


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot calculate mean for empty values")
    return sum(values) / len(values)


def _frequency_components(x_values: list[float], y_values: list[float], frequency_hz: float) -> tuple[float, float]:
    origin = x_values[0]
    n_samples = len(y_values)
    cos_sum = 0.0
    sin_sum = 0.0
    for x_value, y_value in zip(x_values, y_values):
        angle = 2.0 * math.pi * frequency_hz * (x_value - origin)
        cos_sum += y_value * math.cos(angle)
        sin_sum += y_value * math.sin(angle)
    return 2.0 * cos_sum / n_samples, 2.0 * sin_sum / n_samples


def _frequency_amplitude(x_values: list[float], y_values: list[float], frequency_hz: float) -> float:
    cos_coeff, sin_coeff = _frequency_components(x_values, y_values, frequency_hz)
    return math.sqrt(cos_coeff * cos_coeff + sin_coeff * sin_coeff)


def _phasor(x_values: list[float], y_values: list[float], frequency_hz: float) -> complex:
    cos_coeff, sin_coeff = _frequency_components(x_values, y_values, frequency_hz)
    return complex(cos_coeff, -sin_coeff) / math.sqrt(2.0)


def _sliding_rms(times: list[float], values: list[float], cycle_samples: int) -> tuple[list[float], list[float]]:
    window = max(4, int(cycle_samples))
    if len(values) < window:
        raise ValueError(f"Not enough samples for sliding RMS: {len(values)} < {window}")
    out_t: list[float] = []
    out_rms: list[float] = []
    square_sum = sum(value * value for value in values[:window])
    for start in range(0, len(values) - window + 1):
        if start > 0:
            square_sum += values[start + window - 1] * values[start + window - 1] - values[start - 1] * values[start - 1]
        center = start + window // 2
        out_t.append(times[center])
        out_rms.append(math.sqrt(square_sum / window))
    return out_t, out_rms


def _estimate_cycle_samples(x_values: list[float], fundamental_freq: float, configured: Any) -> int:
    if configured is not None:
        return max(4, int(configured))
    sample_rate = _sampling_rate(x_values)
    return max(4, int(round(sample_rate / fundamental_freq)))


def _harmonic_analysis(
    x_values: list[float],
    y_values: list[float],
    *,
    fundamental_freq: float,
    max_harmonic: int,
) -> dict[str, Any]:
    sample_rate = _sampling_rate(x_values)
    nyquist = sample_rate / 2.0
    dc_component = _mean(y_values)
    ac_values = [value - dc_component for value in y_values]
    fundamental_amp = _frequency_amplitude(x_values, ac_values, fundamental_freq)
    fundamental_rms = fundamental_amp / math.sqrt(2.0)
    harmonics: dict[str, Any] = {}
    harmonic_rms_square = 0.0
    max_single = 0.0
    max_single_order = 0
    for order in range(2, max_harmonic + 1):
        frequency = fundamental_freq * order
        if frequency > nyquist:
            break
        amplitude = _frequency_amplitude(x_values, ac_values, frequency)
        harmonic_rms = amplitude / math.sqrt(2.0)
        harmonic_rms_square += harmonic_rms * harmonic_rms
        content_percent = amplitude / fundamental_amp * 100.0 if fundamental_amp > 1e-12 else 0.0
        if content_percent > max_single:
            max_single = content_percent
            max_single_order = order
        harmonics[str(order)] = {
            "frequency_hz": frequency,
            "amplitude": amplitude,
            "rms": harmonic_rms,
            "content_percent": content_percent,
        }
    thd_percent = math.sqrt(harmonic_rms_square) / fundamental_rms * 100.0 if fundamental_rms > 1e-12 else 0.0
    return {
        "sampling_rate_hz": sample_rate,
        "nyquist_hz": nyquist,
        "dc_component": dc_component,
        "rms": _rms(y_values),
        "ac_rms": _rms(ac_values),
        "fundamental": {
            "frequency_hz": fundamental_freq,
            "amplitude": fundamental_amp,
            "rms": fundamental_rms,
        },
        "harmonics": harmonics,
        "thd_percent": thd_percent,
        "max_single_harmonic_percent": max_single,
        "max_single_harmonic_order": max_single_order,
    }


def _event_analysis(
    trace: dict[str, list[float]],
    *,
    event_window: list[float] | tuple[float, float] | None,
    reference_window: list[float] | tuple[float, float] | None,
    fundamental_freq: float,
    cycle_samples: Any,
    min_samples: int,
) -> dict[str, Any]:
    x_raw = trace["x"]
    y_raw = trace["y"]
    event_x, event_y = _window_values(x_raw, y_raw, event_window, default_start=x_raw[0], default_end=x_raw[-1])
    if len(event_x) < min_samples:
        raise ValueError(f"Not enough samples in event window: {len(event_x)} < {min_samples}")
    window_samples = _estimate_cycle_samples(event_x, fundamental_freq, cycle_samples)
    rms_t, rms_values = _sliding_rms(event_x, event_y, window_samples)
    if reference_window:
        _, ref_source = _window_values(rms_t, rms_values, reference_window, default_start=rms_t[0], default_end=rms_t[-1])
    else:
        duration = rms_t[-1] - rms_t[0]
        ref_end = rms_t[0] + min(0.5, max(duration * 0.1, 0.02))
        _, ref_source = _window_values(rms_t, rms_values, None, default_start=rms_t[0], default_end=ref_end)
    if not ref_source:
        ref_source = rms_values[: max(1, min(5, len(rms_values)))]
    reference_rms = _mean(ref_source)
    min_rms = min(rms_values)
    max_rms = max(rms_values)
    min_index = rms_values.index(min_rms)
    max_index = rms_values.index(max_rms)
    dip_percent = (reference_rms - min_rms) / reference_rms * 100.0 if reference_rms > 1e-12 else 0.0
    swell_percent = (max_rms - reference_rms) / reference_rms * 100.0 if reference_rms > 1e-12 else 0.0
    modulation = [abs(value - reference_rms) / reference_rms * 100.0 for value in rms_values] if reference_rms > 1e-12 else [0.0]
    flicker_proxy = math.sqrt(sum(value * value for value in modulation) / len(modulation))
    return {
        "cycle_samples": window_samples,
        "rms_window_count": len(rms_values),
        "reference_rms": reference_rms,
        "min_rms": min_rms,
        "min_rms_time_s": rms_t[min_index],
        "max_rms": max_rms,
        "max_rms_time_s": rms_t[max_index],
        "dip_percent": max(0.0, dip_percent),
        "swell_percent": max(0.0, swell_percent),
        "flicker_proxy_percent": flicker_proxy,
    }


def analyze_single_trace(
    trace: dict[str, list[float]],
    *,
    fundamental_freq: float,
    max_harmonic: int,
    analysis_window: list[float] | tuple[float, float] | None,
    event_window: list[float] | tuple[float, float] | None,
    reference_window: list[float] | tuple[float, float] | None,
    cycle_samples: Any,
    min_samples: int,
) -> dict[str, Any]:
    x_raw = trace["x"]
    y_raw = trace["y"]
    default_start, default_end = _default_analysis_window(x_raw)
    win_x, win_y = _window_values(x_raw, y_raw, analysis_window, default_start=default_start, default_end=default_end)
    if len(win_x) < min_samples:
        raise ValueError(f"Not enough samples in analysis window: {len(win_x)} < {min_samples}")
    harmonic = _harmonic_analysis(win_x, win_y, fundamental_freq=fundamental_freq, max_harmonic=max_harmonic)
    event = _event_analysis(
        trace,
        event_window=event_window,
        reference_window=reference_window,
        fundamental_freq=fundamental_freq,
        cycle_samples=cycle_samples,
        min_samples=min_samples,
    )
    dc_offset_percent = abs(harmonic["dc_component"]) / harmonic["ac_rms"] * 100.0 if harmonic["ac_rms"] > 1e-12 else 0.0
    return {
        "sample_count": len(win_x),
        "t_start": win_x[0],
        "t_end": win_x[-1],
        "rms": harmonic["rms"],
        "ac_rms": harmonic["ac_rms"],
        "dc_component": harmonic["dc_component"],
        "dc_offset_percent": dc_offset_percent,
        "fundamental": harmonic["fundamental"],
        "harmonics": harmonic["harmonics"],
        "thd_percent": harmonic["thd_percent"],
        "max_single_harmonic_percent": harmonic["max_single_harmonic_percent"],
        "max_single_harmonic_order": harmonic["max_single_harmonic_order"],
        "voltage_event": event,
    }


def analyze_three_phase_group(
    traces: dict[str, dict[str, list[float]]],
    *,
    fundamental_freq: float,
    analysis_window: list[float] | tuple[float, float] | None,
    min_samples: int,
) -> dict[str, Any]:
    a = traces["a"]
    b = traces["b"]
    c = traces["c"]
    if a["x"] != b["x"] or a["x"] != c["x"]:
        raise ValueError("Three-phase traces must share the same time axis")
    default_start, default_end = _default_analysis_window(a["x"])
    x_values, va = _window_values(a["x"], a["y"], analysis_window, default_start=default_start, default_end=default_end)
    _, vb = _window_values(b["x"], b["y"], analysis_window, default_start=default_start, default_end=default_end)
    _, vc = _window_values(c["x"], c["y"], analysis_window, default_start=default_start, default_end=default_end)
    if len(x_values) < min_samples:
        raise ValueError(f"Not enough samples in three-phase analysis window: {len(x_values)} < {min_samples}")
    rms_a = _rms(va)
    rms_b = _rms(vb)
    rms_c = _rms(vc)
    avg_rms = (rms_a + rms_b + rms_c) / 3.0
    rms_unbalance = max(abs(rms_a - avg_rms), abs(rms_b - avg_rms), abs(rms_c - avg_rms)) / avg_rms * 100.0 if avg_rms > 1e-12 else 0.0
    phasor_a = _phasor(x_values, [value - _mean(va) for value in va], fundamental_freq)
    phasor_b = _phasor(x_values, [value - _mean(vb) for value in vb], fundamental_freq)
    phasor_c = _phasor(x_values, [value - _mean(vc) for value in vc], fundamental_freq)
    alpha = complex(-0.5, math.sqrt(3.0) / 2.0)
    positive = (phasor_a + alpha * phasor_b + alpha * alpha * phasor_c) / 3.0
    negative = (phasor_a + alpha * alpha * phasor_b + alpha * phasor_c) / 3.0
    sequence_unbalance = abs(negative) / abs(positive) * 100.0 if abs(positive) > 1e-12 else 0.0
    return {
        "sample_count": len(x_values),
        "t_start": x_values[0],
        "t_end": x_values[-1],
        "rms_a": rms_a,
        "rms_b": rms_b,
        "rms_c": rms_c,
        "avg_rms": avg_rms,
        "rms_unbalance_percent": rms_unbalance,
        "sequence_positive_rms": abs(positive),
        "sequence_negative_rms": abs(negative),
        "sequence_unbalance_percent": sequence_unbalance,
    }


def _status(value: float, limit: float) -> str:
    return "PASS" if value <= limit else "VIOLATION"


def _summarize(single_rows: list[dict[str, Any]], three_phase_rows: list[dict[str, Any]], limits: dict[str, float]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for row in single_rows:
        channel = row["channel"]
        analysis = row["analysis"]
        checks = [
            ("thd", analysis["thd_percent"], limits["thd_percent"]),
            ("single_harmonic", analysis["max_single_harmonic_percent"], limits["single_harmonic_percent"]),
            ("voltage_dip", analysis["voltage_event"]["dip_percent"], limits["voltage_dip_percent"]),
            ("voltage_swell", analysis["voltage_event"]["swell_percent"], limits["voltage_swell_percent"]),
            ("dc_offset", analysis["dc_offset_percent"], limits["dc_offset_percent"]),
            ("flicker_proxy", analysis["voltage_event"]["flicker_proxy_percent"], limits["flicker_proxy_percent"]),
        ]
        for indicator, value, limit in checks:
            if value > limit:
                violations.append({"indicator": indicator, "channel": channel, "value": value, "limit": limit})
    for row in three_phase_rows:
        analysis = row["analysis"]
        value = max(analysis["rms_unbalance_percent"], analysis["sequence_unbalance_percent"])
        if value > limits["unbalance_percent"]:
            violations.append({"indicator": "unbalance", "channel": row["name"], "value": value, "limit": limits["unbalance_percent"]})

    max_thd = max((row["analysis"]["thd_percent"] for row in single_rows), default=0.0)
    max_dip = max((row["analysis"]["voltage_event"]["dip_percent"] for row in single_rows), default=0.0)
    max_swell = max((row["analysis"]["voltage_event"]["swell_percent"] for row in single_rows), default=0.0)
    max_dc = max((row["analysis"]["dc_offset_percent"] for row in single_rows), default=0.0)
    max_flicker = max((row["analysis"]["voltage_event"]["flicker_proxy_percent"] for row in single_rows), default=0.0)
    max_unbalance = max(
        (max(row["analysis"]["rms_unbalance_percent"], row["analysis"]["sequence_unbalance_percent"]) for row in three_phase_rows),
        default=0.0,
    )
    return {
        "channel_count": len(single_rows),
        "three_phase_group_count": len(three_phase_rows),
        "max_thd_percent": max_thd,
        "max_voltage_dip_percent": max_dip,
        "max_voltage_swell_percent": max_swell,
        "max_unbalance_percent": max_unbalance,
        "max_dc_offset_percent": max_dc,
        "max_flicker_proxy_percent": max_flicker,
        "violation_count": len(violations),
        "overall_status": "PASS" if not violations else "VIOLATION",
        "violations": violations,
    }


def _write_artifacts(result_data: dict[str, Any], output_dir: Path, prefix: str, *, generate_report: bool, export_harmonics: bool) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / f"{prefix}_{timestamp}.csv"
    limits = result_data["analysis"]["limits"]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["indicator", "channel", "value", "limit", "status", "detail"])
        for row in result_data["channels"]:
            analysis = row["analysis"]
            event = analysis["voltage_event"]
            rows = [
                ("thd", analysis["thd_percent"], limits["thd_percent"], f"max_single_h={analysis['max_single_harmonic_order']}"),
                ("single_harmonic", analysis["max_single_harmonic_percent"], limits["single_harmonic_percent"], f"order={analysis['max_single_harmonic_order']}"),
                ("voltage_dip", event["dip_percent"], limits["voltage_dip_percent"], f"min_rms={event['min_rms']:.9g}"),
                ("voltage_swell", event["swell_percent"], limits["voltage_swell_percent"], f"max_rms={event['max_rms']:.9g}"),
                ("dc_offset", analysis["dc_offset_percent"], limits["dc_offset_percent"], f"dc={analysis['dc_component']:.9g}"),
                ("flicker_proxy", event["flicker_proxy_percent"], limits["flicker_proxy_percent"], "rms_modulation_proxy"),
            ]
            for indicator, value, limit, detail in rows:
                writer.writerow([indicator, row["channel"], f"{value:.9g}", f"{limit:.9g}", _status(value, limit), detail])
        for row in result_data["three_phase_groups"]:
            analysis = row["analysis"]
            value = max(analysis["rms_unbalance_percent"], analysis["sequence_unbalance_percent"])
            writer.writerow(["unbalance", row["name"], f"{value:.9g}", f"{limits['unbalance_percent']:.9g}", _status(value, limits["unbalance_percent"]), "max(rms_unbalance, sequence_unbalance)"])

    harmonics_path = output_dir / f"{prefix}_harmonics_{timestamp}.csv"
    if export_harmonics:
        with harmonics_path.open("w", newline="", encoding="utf-8") as harmonics_file:
            writer = csv.writer(harmonics_file)
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
        harmonics_path = Path("")

    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        summary = result_data["summary"]
        lines = [
            "# Power Quality Analysis Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Job ID: `{result_data['job_id']}`",
            f"- Fundamental: `{result_data['analysis']['fundamental_freq']} Hz`",
            f"- Overall status: `{summary['overall_status']}`",
            f"- Violations: `{summary['violation_count']}`",
            f"- Max THD: `{summary['max_thd_percent']:.6f}%`",
            f"- Max voltage dip: `{summary['max_voltage_dip_percent']:.6f}%`",
            f"- Max unbalance: `{summary['max_unbalance_percent']:.6f}%`",
            "",
            "## Single-Channel Indicators",
            "",
            "| kind | channel | rms | THD % | dip % | swell % | dc offset % | flicker proxy % |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in result_data["channels"]:
            analysis = row["analysis"]
            event = analysis["voltage_event"]
            lines.append(
                f"| {row['kind']} | `{row['channel']}` | {analysis['rms']:.6f} | "
                f"{analysis['thd_percent']:.6f} | {event['dip_percent']:.6f} | {event['swell_percent']:.6f} | "
                f"{analysis['dc_offset_percent']:.6f} | {event['flicker_proxy_percent']:.6f} |"
            )
        lines.extend(
            [
                "",
                "## Three-Phase Indicators",
                "",
                "| group | A rms | B rms | C rms | RMS unbalance % | sequence unbalance % |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in result_data["three_phase_groups"]:
            analysis = row["analysis"]
            lines.append(
                f"| `{row['name']}` | {analysis['rms_a']:.6f} | {analysis['rms_b']:.6f} | "
                f"{analysis['rms_c']:.6f} | {analysis['rms_unbalance_percent']:.6f} | "
                f"{analysis['sequence_unbalance_percent']:.6f} |"
            )
        if summary["violations"]:
            lines.extend(["", "## Violations", "", "| indicator | channel | value | limit |", "| --- | --- | ---: | ---: |"])
            for item in summary["violations"]:
                lines.append(f"| {item['indicator']} | `{item['channel']}` | {item['value']:.6f} | {item['limit']:.6f} |")
        lines.extend(
            [
                "",
                "## Engineering Notes",
                "",
                "- Harmonics are estimated by projection at configured harmonic frequencies.",
                "- Voltage dip and swell are estimated from sliding RMS values.",
                "- Flicker proxy is short-window RMS modulation, not IEC Pst/Plt.",
                "- This skill analyzes existing EMT outputs and does not modify or save the CloudPSS model.",
            ]
        )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = Path("")

    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "harmonics_csv_path": str(harmonics_path) if harmonics_path else "",
        "markdown_path": str(markdown_path) if markdown_path else "",
    }


def run_power_quality_analysis(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None, timeout: int = 300) -> dict[str, Any]:
    resolved = _resolve_config(config)
    job = run_emt(model, timeout=timeout)
    selected = _select_traces(job.result, resolved["channels"], resolved["auto_max_channels"])

    single_rows: list[dict[str, Any]] = []
    for item in selected:
        analysis = analyze_single_trace(
            item["trace"],
            fundamental_freq=resolved["fundamental_freq"],
            max_harmonic=resolved["max_harmonic"],
            analysis_window=resolved["analysis_window"],
            event_window=resolved["event_window"],
            reference_window=resolved["reference_window"],
            cycle_samples=resolved["cycle_samples"],
            min_samples=resolved["min_samples"],
        )
        single_rows.append(
            {
                "kind": item["kind"],
                "plot_index": item["plot_index"],
                "plot": item["plot"],
                "channel": item["channel"],
                "analysis": analysis,
            }
        )

    three_phase_rows: list[dict[str, Any]] = []
    for index, group in enumerate(resolved["three_phase"], 1):
        if not isinstance(group, dict):
            raise ValueError("channels.three_phase entries must be objects")
        name = str(group.get("name") or f"three_phase_{index}")
        channels = {"a": str(group.get("a", "")), "b": str(group.get("b", "")), "c": str(group.get("c", ""))}
        if not channels["a"] or not channels["b"] or not channels["c"]:
            raise ValueError("three_phase group requires a, b and c channel names")
        traces: dict[str, dict[str, list[float]]] = {}
        plot_indexes: dict[str, int] = {}
        for phase, channel_name in channels.items():
            plot_index, _plot, trace = _find_trace(job.result, channel_name)
            traces[phase] = trace
            plot_indexes[phase] = plot_index
        analysis = analyze_three_phase_group(
            traces,
            fundamental_freq=resolved["fundamental_freq"],
            analysis_window=resolved["analysis_window"],
            min_samples=resolved["min_samples"],
        )
        three_phase_rows.append(
            {
                "name": name,
                "channels": channels,
                "plot_indexes": plot_indexes,
                "analysis": analysis,
            }
        )

    if not single_rows and not three_phase_rows:
        raise RuntimeError("No channels analyzed")

    summary = _summarize(single_rows, three_phase_rows, resolved["limits"])
    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "job_id": getattr(job, "id", None),
        "analysis": {
            "fundamental_freq": resolved["fundamental_freq"],
            "max_harmonic": resolved["max_harmonic"],
            "analysis_window": resolved["analysis_window"],
            "event_window": resolved["event_window"],
            "reference_window": resolved["reference_window"],
            "min_samples": resolved["min_samples"],
            "limits": resolved["limits"],
        },
        "summary": summary,
        "channels": single_rows,
        "three_phase_groups": three_phase_rows,
    }

    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "power_quality_analysis")
    artifacts = _write_artifacts(
        result_data,
        target_dir,
        prefix,
        generate_report=bool(output_config.get("generate_report", True)),
        export_harmonics=bool(output_config.get("export_harmonics", True)),
    )
    return {**result_data, "artifacts": artifacts}
