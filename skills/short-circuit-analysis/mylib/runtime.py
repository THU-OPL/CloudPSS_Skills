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
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "short-circuit-analysis"


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
    thevenin = config.get("thevenin", analysis.get("thevenin", {}))
    channels = config.get("channels", {})
    output = config.get("output", {})
    return {
        "base_voltage_kv": float(analysis.get("base_voltage_kv", analysis.get("base_voltage", 230.0))),
        "current_scale": float(analysis.get("current_scale", 1.0)),
        "power_scale_mw": float(analysis.get("power_scale_mw", 1.0)),
        "voltage_scale_pu": float(analysis.get("voltage_scale_pu", 1.0)),
        "nominal_voltage_pu": float(analysis.get("nominal_voltage_pu", 1.0)),
        "analysis_window": analysis.get("analysis_window"),
        "prefault_window": analysis.get("prefault_window"),
        "fault_window": analysis.get("fault_window"),
        "postfault_window": analysis.get("postfault_window"),
        "min_samples": int(analysis.get("min_samples", 128)),
        "auto_max_channels": int(channels.get("auto_max_channels", 3)),
        "thevenin": {
            "enabled": bool(thevenin.get("enabled", analysis.get("enable_thevenin", True))),
            "system_base_mva": float(thevenin.get("system_base_mva", analysis.get("system_base_mva", 100.0))),
            "plant_rating_mva": _optional_float(
                thevenin.get("plant_rating_mva", thevenin.get("rating_mva", analysis.get("plant_rating_mva")))
            ),
            "reactive_compensation_mvar": _optional_float(
                thevenin.get("reactive_compensation_mvar", thevenin.get("shunt_compensation_mvar", 0.0))
            ),
            "xr_ratio": _optional_float(thevenin.get("xr_ratio", analysis.get("xr_ratio"))),
            "weak_scr_threshold": float(thevenin.get("weak_scr_threshold", 2.0)),
            "strong_scr_threshold": float(thevenin.get("strong_scr_threshold", 3.0)),
        },
        "channels": {
            "current": list(channels.get("current", [])),
            "voltage": list(channels.get("voltage", [])),
            "power": list(channels.get("power", [])),
            "reactive_power": list(channels.get("reactive_power", [])),
            "generic": list(channels.get("generic", [])),
        },
        "equivalent_pairs": list(channels.get("equivalent_pairs", [])),
        "output": output,
    }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


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


def _looks_like_current_channel(channel_name: str) -> bool:
    lower = channel_name.lower()
    if "wr" in lower or "theta" in lower or "freq" in lower:
        return False
    current_tokens = ("i", "ia", "ib", "ic", "irms", "it", "current")
    return any(token in lower for token in current_tokens)


def _auto_select_current_traces(result, max_channels: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for plot_index, plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            if not _looks_like_current_channel(channel_name):
                continue
            data = result.getPlotChannelData(plot_index, channel_name)
            if not data:
                continue
            x_values = [float(value) for value in data.get("x", [])]
            y_values = [float(value) for value in data.get("y", [])]
            if len(x_values) > 1 and len(x_values) == len(y_values):
                selected.append(
                    {
                        "kind": "current",
                        "channel": channel_name,
                        "plot_index": plot_index,
                        "plot": _plot_name(plot, plot_index),
                        "trace": {"x": x_values, "y": y_values},
                    }
                )
            if len(selected) >= max_channels:
                return selected
    return selected


def _select_explicit_traces(result, channel_config: dict[str, list[str]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for kind, names in channel_config.items():
        if kind in {"power", "reactive_power"}:
            continue
        for channel_name in names:
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


def _rms(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot calculate RMS for empty values")
    return math.sqrt(sum(value * value for value in values) / len(values))


def _mean_abs(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot calculate mean for empty values")
    return sum(abs(value) for value in values) / len(values)


def _peak(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot calculate peak for empty values")
    return max(abs(value) for value in values)


def _validate_time_axis(x_values: list[float]) -> None:
    if any(x_values[index] >= x_values[index + 1] for index in range(len(x_values) - 1)):
        raise ValueError("Waveform time axis is not strictly increasing")


def _default_windows(x_values: list[float]) -> dict[str, tuple[float, float]]:
    start = x_values[0]
    end = x_values[-1]
    duration = end - start
    if duration <= 0:
        raise ValueError("Invalid time axis duration")
    early_end = start + min(0.5, duration * 0.2)
    mid_start = start + duration * 0.2
    mid_end = start + duration * 0.8
    late_start = end - min(0.5, duration * 0.2)
    return {
        "prefault": (start, early_end),
        "fault": (mid_start, mid_end),
        "postfault": (late_start, end),
    }


def _short_circuit_mva(current_rms: float, base_voltage_kv: float) -> float:
    return math.sqrt(3.0) * base_voltage_kv * abs(current_rms)


def _grid_strength(scr: float | None, weak_threshold: float, strong_threshold: float) -> str:
    if scr is None:
        return "not_assessed"
    if scr < weak_threshold:
        return "weak"
    if scr < strong_threshold:
        return "medium"
    return "strong"


def _grid_strength_note(strength: str) -> str:
    notes = {
        "strong": "Short-circuit strength is above the configured strong-grid threshold.",
        "medium": "Short-circuit strength is in the intermediate range; voltage/reactive support and controls should be reviewed.",
        "weak": "Short-circuit strength is below the configured weak-grid threshold; detailed IBR/control interaction studies are recommended.",
        "not_assessed": "Plant rating was not provided, so SCR/ESCR was not assessed.",
    }
    return notes.get(strength, "Unknown grid-strength classification.")


def _thevenin_from_short_circuit(
    *,
    short_circuit_mva: float,
    base_voltage_kv: float,
    system_base_mva: float,
    plant_rating_mva: float | None,
    reactive_compensation_mvar: float | None,
    xr_ratio: float | None,
    weak_scr_threshold: float,
    strong_scr_threshold: float,
) -> dict[str, Any]:
    if short_circuit_mva <= 0:
        raise ValueError("short_circuit_mva must be positive to compute Thevenin equivalent")
    if base_voltage_kv <= 0:
        raise ValueError("base_voltage_kv must be positive to compute Thevenin equivalent")
    if system_base_mva <= 0:
        raise ValueError("system_base_mva must be positive to compute Thevenin equivalent")

    z_base_ohm = base_voltage_kv * base_voltage_kv / system_base_mva
    z_th_ohm_mag = base_voltage_kv * base_voltage_kv / short_circuit_mva
    z_th_pu_mag = system_base_mva / short_circuit_mva
    z_ohm: dict[str, Any] = {
        "magnitude": z_th_ohm_mag,
        "real": None,
        "imag": None,
        "xr_ratio": xr_ratio,
    }
    z_pu: dict[str, Any] = {
        "magnitude": z_th_pu_mag,
        "real": None,
        "imag": None,
        "xr_ratio": xr_ratio,
    }
    if xr_ratio is not None and xr_ratio > 0:
        r_ohm = z_th_ohm_mag / math.sqrt(1.0 + xr_ratio * xr_ratio)
        x_ohm = r_ohm * xr_ratio
        r_pu = z_th_pu_mag / math.sqrt(1.0 + xr_ratio * xr_ratio)
        x_pu = r_pu * xr_ratio
        z_ohm.update({"real": r_ohm, "imag": x_ohm})
        z_pu.update({"real": r_pu, "imag": x_pu})

    scr = None
    escr = None
    q_comp = reactive_compensation_mvar if reactive_compensation_mvar is not None else 0.0
    if plant_rating_mva is not None and plant_rating_mva > 0:
        scr = short_circuit_mva / plant_rating_mva
        escr = (short_circuit_mva - q_comp) / plant_rating_mva

    strength_basis = escr if escr is not None else scr
    strength = _grid_strength(strength_basis, weak_scr_threshold, strong_scr_threshold)
    return {
        "method": "derived_from_short_circuit_capacity",
        "formula": "Zth=Vll^2/Ssc; SCR=Ssc/Srated; ESCR=(Ssc-Qcomp)/Srated",
        "base_voltage_kv": base_voltage_kv,
        "system_base_mva": system_base_mva,
        "z_base_ohm": z_base_ohm,
        "z_th_ohm": z_ohm,
        "z_th_pu": z_pu,
        "short_circuit_capacity_mva": short_circuit_mva,
        "plant_rating_mva": plant_rating_mva,
        "reactive_compensation_mvar": q_comp,
        "scr": scr,
        "escr": escr,
        "weak_scr_threshold": weak_scr_threshold,
        "strong_scr_threshold": strong_scr_threshold,
        "grid_strength": strength,
        "assessment": _grid_strength_note(strength),
    }


def analyze_short_circuit_trace(
    trace: dict[str, list[float]],
    *,
    kind: str,
    base_voltage_kv: float,
    current_scale: float,
    analysis_window: list[float] | tuple[float, float] | None,
    prefault_window: list[float] | tuple[float, float] | None,
    fault_window: list[float] | tuple[float, float] | None,
    postfault_window: list[float] | tuple[float, float] | None,
    min_samples: int,
) -> dict[str, Any]:
    x_raw = trace["x"]
    y_raw = [value * current_scale if kind == "current" else value for value in trace["y"]]
    _validate_time_axis(x_raw)

    total_start = x_raw[0]
    total_end = x_raw[-1]
    win_x, win_y = _window_values(x_raw, y_raw, analysis_window, default_start=total_start, default_end=total_end)
    if len(win_x) < min_samples:
        raise ValueError(f"Not enough samples in analysis window: {len(win_x)} < {min_samples}")

    defaults = _default_windows(win_x)
    _, prefault_values = _window_values(win_x, win_y, prefault_window, default_start=defaults["prefault"][0], default_end=defaults["prefault"][1])
    fault_x, fault_values = _window_values(win_x, win_y, fault_window, default_start=defaults["fault"][0], default_end=defaults["fault"][1])
    _, postfault_values = _window_values(win_x, win_y, postfault_window, default_start=defaults["postfault"][0], default_end=defaults["postfault"][1])
    if not prefault_values or not fault_values or not postfault_values:
        raise ValueError("One or more analysis windows contain no data")

    peak_current = _peak(win_y)
    fault_peak = _peak(fault_values)
    prefault_rms = _rms(prefault_values)
    fault_rms = _rms(fault_values)
    postfault_rms = _rms(postfault_values)
    dc_offset = _mean_abs(fault_values) - _rms(fault_values) / math.sqrt(2.0)
    min_current = min(win_y)
    max_current = max(win_y)
    max_index = max(range(len(win_y)), key=lambda index: abs(win_y[index]))

    return {
        "method": "direct_current_channel" if kind == "current" else "generic_waveform",
        "sample_count": len(win_x),
        "t_start": win_x[0],
        "t_end": win_x[-1],
        "fault_window_start": fault_x[0],
        "fault_window_end": fault_x[-1],
        "min_current": min_current,
        "max_current": max_current,
        "peak_current": peak_current,
        "peak_current_time_s": win_x[max_index],
        "fault_peak_current": fault_peak,
        "prefault_rms_current": prefault_rms,
        "fault_rms_current": fault_rms,
        "postfault_rms_current": postfault_rms,
        "fault_to_prefault_rms_ratio": fault_rms / prefault_rms if prefault_rms > 1e-12 else None,
        "postfault_to_prefault_rms_ratio": postfault_rms / prefault_rms if prefault_rms > 1e-12 else None,
        "dc_offset_estimate": dc_offset,
        "short_circuit_mva": _short_circuit_mva(fault_rms, base_voltage_kv),
    }


def _equivalent_current_trace(
    power_trace: dict[str, list[float]],
    voltage_trace: dict[str, list[float]],
    *,
    power_scale_mw: float,
    voltage_scale_pu: float,
    base_voltage_kv: float,
    nominal_voltage_pu: float,
) -> dict[str, list[float]]:
    p_x = power_trace["x"]
    p_y = power_trace["y"]
    v_x = voltage_trace["x"]
    v_y = voltage_trace["y"]
    if len(p_x) != len(v_x) or any(abs(a - b) > 1e-9 for a, b in zip(p_x, v_x)):
        raise ValueError("Power and voltage traces must share the same time axis")

    currents: list[float] = []
    for p_value, v_value in zip(p_y, v_y):
        voltage_pu = abs(v_value * voltage_scale_pu)
        if voltage_pu < 1e-6:
            voltage_pu = nominal_voltage_pu
        # S(MVA) = sqrt(3) * V(kV) * I(kA), so I(kA) = P(MW) / (sqrt(3) * V(kV)).
        current_ka = abs(p_value * power_scale_mw) / (math.sqrt(3.0) * base_voltage_kv * voltage_pu)
        currents.append(current_ka)
    return {"x": list(p_x), "y": currents}


def _select_equivalent_pairs(result, pairs: list[Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for pair in pairs:
        if not isinstance(pair, dict):
            raise ValueError("equivalent_pairs entries must be objects")
        power_channel = pair.get("power")
        voltage_channel = pair.get("voltage")
        if not power_channel or not voltage_channel:
            raise ValueError("equivalent_pairs requires power and voltage fields")
        p_plot_index, p_plot, p_trace = _find_trace(result, str(power_channel))
        _, _, v_trace = _find_trace(result, str(voltage_channel))
        selected.append(
            {
                "kind": "equivalent_current",
                "channel": f"{power_channel}|{voltage_channel}",
                "plot_index": p_plot_index,
                "plot": p_plot,
                "trace": p_trace,
                "voltage_trace": v_trace,
                "power_channel": str(power_channel),
                "voltage_channel": str(voltage_channel),
            }
        )
    return selected


def _auto_equivalent_pairs(result, max_channels: int) -> list[dict[str, Any]]:
    power_names: list[str] = []
    voltage_names: list[str] = []
    for plot_index, _plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            lower = channel_name.lower()
            if lower.startswith("#p"):
                power_names.append(channel_name)
            elif lower.startswith("v") or "vac" in lower or "vrms" in lower:
                voltage_names.append(channel_name)
    pairs: list[dict[str, str]] = []
    for index, power_name in enumerate(power_names[:max_channels]):
        voltage_name = voltage_names[index] if index < len(voltage_names) else voltage_names[0] if voltage_names else ""
        if voltage_name:
            pairs.append({"power": power_name, "voltage": voltage_name})
    return _select_equivalent_pairs(result, pairs)


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
                "method",
                "sample_count",
                "peak_current",
                "fault_rms_current",
                "prefault_rms_current",
                "postfault_rms_current",
                "short_circuit_mva",
                "fault_to_prefault_rms_ratio",
                "z_th_pu_magnitude",
                "z_th_ohm_magnitude",
                "scr",
                "escr",
                "grid_strength",
            ]
        )
        for row in result_data["channels"]:
            analysis = row["analysis"]
            thevenin = analysis.get("thevenin", {})
            z_pu = thevenin.get("z_th_pu", {}) if thevenin else {}
            z_ohm = thevenin.get("z_th_ohm", {}) if thevenin else {}
            writer.writerow(
                [
                    row["kind"],
                    row["plot_index"],
                    row["channel"],
                    analysis["method"],
                    analysis["sample_count"],
                    f"{analysis['peak_current']:.9g}",
                    f"{analysis['fault_rms_current']:.9g}",
                    f"{analysis['prefault_rms_current']:.9g}",
                    f"{analysis['postfault_rms_current']:.9g}",
                    f"{analysis['short_circuit_mva']:.9g}",
                    "" if analysis["fault_to_prefault_rms_ratio"] is None else f"{analysis['fault_to_prefault_rms_ratio']:.9g}",
                    "" if not z_pu else f"{z_pu['magnitude']:.9g}",
                    "" if not z_ohm else f"{z_ohm['magnitude']:.9g}",
                    "" if thevenin.get("scr") is None else f"{thevenin['scr']:.9g}",
                    "" if thevenin.get("escr") is None else f"{thevenin['escr']:.9g}",
                    thevenin.get("grid_strength", ""),
                ]
            )

    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        lines = [
            "# Short Circuit Analysis Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Job ID: `{result_data['job_id']}`",
            f"- Base voltage: `{result_data['analysis']['base_voltage_kv']} kV`",
            f"- Max fault RMS current: `{result_data['summary']['max_fault_rms_current']:.6f}`",
            f"- Max short-circuit capacity: `{result_data['summary']['max_short_circuit_mva']:.6f} MVA`",
            f"- Estimation methods: `{', '.join(result_data['summary']['methods'])}`",
        ]
        if result_data.get("thevenin", {}).get("enabled"):
            lines.extend(
                [
                    f"- Minimum SCR: `{_format_optional(result_data['thevenin']['summary'].get('min_scr'))}`",
                    f"- Minimum ESCR: `{_format_optional(result_data['thevenin']['summary'].get('min_escr'))}`",
                    f"- Worst grid strength: `{result_data['thevenin']['summary'].get('worst_grid_strength', 'not_assessed')}`",
                ]
            )
        lines.extend(
            [
                "",
                "| kind | channel | method | peak | fault RMS | prefault RMS | postfault RMS | Ssc MVA |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in result_data["channels"]:
            analysis = row["analysis"]
            lines.append(
                f"| {row['kind']} | `{row['channel']}` | {analysis['method']} | "
                f"{analysis['peak_current']:.6f} | {analysis['fault_rms_current']:.6f} | "
                f"{analysis['prefault_rms_current']:.6f} | {analysis['postfault_rms_current']:.6f} | "
                f"{analysis['short_circuit_mva']:.6f} |"
            )
        if result_data.get("thevenin", {}).get("enabled"):
            lines.extend(
                [
                    "",
                    "## Thevenin Equivalent and SCR",
                    "",
                    "| channel | Zth pu | Zth ohm | SCR | ESCR | grid strength |",
                    "| --- | ---: | ---: | ---: | ---: | --- |",
                ]
            )
            for row in result_data["channels"]:
                thevenin = row["analysis"].get("thevenin")
                if not thevenin:
                    continue
                lines.append(
                    f"| `{row['channel']}` | {thevenin['z_th_pu']['magnitude']:.6f} | "
                    f"{thevenin['z_th_ohm']['magnitude']:.6f} | "
                    f"{_format_optional(thevenin.get('scr'))} | {_format_optional(thevenin.get('escr'))} | "
                    f"{thevenin['grid_strength']} |"
                )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = Path("")

    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "markdown_path": str(markdown_path) if markdown_path else "",
    }


def _format_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _summarize_thevenin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    thevenin_rows = [row["analysis"]["thevenin"] for row in rows if row["analysis"].get("thevenin")]
    if not thevenin_rows:
        return {
            "enabled": False,
            "channel_count": 0,
        }
    scr_values = [row["scr"] for row in thevenin_rows if row.get("scr") is not None]
    escr_values = [row["escr"] for row in thevenin_rows if row.get("escr") is not None]
    strength_rank = {"weak": 0, "medium": 1, "strong": 2, "not_assessed": 3}
    worst = min((row["grid_strength"] for row in thevenin_rows), key=lambda item: strength_rank.get(item, 99))
    return {
        "enabled": True,
        "channel_count": len(thevenin_rows),
        "min_z_th_pu_magnitude": min(row["z_th_pu"]["magnitude"] for row in thevenin_rows),
        "max_z_th_pu_magnitude": max(row["z_th_pu"]["magnitude"] for row in thevenin_rows),
        "min_z_th_ohm_magnitude": min(row["z_th_ohm"]["magnitude"] for row in thevenin_rows),
        "max_z_th_ohm_magnitude": max(row["z_th_ohm"]["magnitude"] for row in thevenin_rows),
        "min_scr": min(scr_values) if scr_values else None,
        "min_escr": min(escr_values) if escr_values else None,
        "worst_grid_strength": worst,
    }


def run_short_circuit_analysis(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None, timeout: int = 300) -> dict[str, Any]:
    resolved = _resolve_config(config)
    job = run_emt(model, timeout=timeout)

    selected = _select_explicit_traces(job.result, resolved["channels"])
    if not selected:
        selected = _auto_select_current_traces(job.result, resolved["auto_max_channels"])

    equivalent_selected = _select_equivalent_pairs(job.result, resolved["equivalent_pairs"]) if resolved["equivalent_pairs"] else []
    if not selected and not equivalent_selected:
        equivalent_selected = _auto_equivalent_pairs(job.result, resolved["auto_max_channels"])

    rows: list[dict[str, Any]] = []
    for item in selected:
        analysis = analyze_short_circuit_trace(
            item["trace"],
            kind=item["kind"],
            base_voltage_kv=resolved["base_voltage_kv"],
            current_scale=resolved["current_scale"],
            analysis_window=resolved["analysis_window"],
            prefault_window=resolved["prefault_window"],
            fault_window=resolved["fault_window"],
            postfault_window=resolved["postfault_window"],
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

    for item in equivalent_selected:
        eq_trace = _equivalent_current_trace(
            item["trace"],
            item["voltage_trace"],
            power_scale_mw=resolved["power_scale_mw"],
            voltage_scale_pu=resolved["voltage_scale_pu"],
            base_voltage_kv=resolved["base_voltage_kv"],
            nominal_voltage_pu=resolved["nominal_voltage_pu"],
        )
        analysis = analyze_short_circuit_trace(
            eq_trace,
            kind="current",
            base_voltage_kv=resolved["base_voltage_kv"],
            current_scale=1.0,
            analysis_window=resolved["analysis_window"],
            prefault_window=resolved["prefault_window"],
            fault_window=resolved["fault_window"],
            postfault_window=resolved["postfault_window"],
            min_samples=resolved["min_samples"],
        )
        analysis["method"] = "estimated_from_power_voltage"
        rows.append(
            {
                "kind": "equivalent_current",
                "plot_index": item["plot_index"],
                "plot": item["plot"],
                "channel": item["channel"],
                "source_channels": {
                    "power": item["power_channel"],
                    "voltage": item["voltage_channel"],
                },
                "analysis": analysis,
            }
        )

    if not rows:
        raise RuntimeError("No channels analyzed")

    if resolved["thevenin"]["enabled"]:
        for row in rows:
            row["analysis"]["thevenin"] = _thevenin_from_short_circuit(
                short_circuit_mva=row["analysis"]["short_circuit_mva"],
                base_voltage_kv=resolved["base_voltage_kv"],
                system_base_mva=resolved["thevenin"]["system_base_mva"],
                plant_rating_mva=resolved["thevenin"]["plant_rating_mva"],
                reactive_compensation_mvar=resolved["thevenin"]["reactive_compensation_mvar"],
                xr_ratio=resolved["thevenin"]["xr_ratio"],
                weak_scr_threshold=resolved["thevenin"]["weak_scr_threshold"],
                strong_scr_threshold=resolved["thevenin"]["strong_scr_threshold"],
            )

    max_peak = max(row["analysis"]["peak_current"] for row in rows)
    max_fault_rms = max(row["analysis"]["fault_rms_current"] for row in rows)
    max_scc = max(row["analysis"]["short_circuit_mva"] for row in rows)
    thevenin_summary = _summarize_thevenin(rows) if resolved["thevenin"]["enabled"] else {"enabled": False, "channel_count": 0}
    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "job_id": getattr(job, "id", None),
        "analysis": {
            "base_voltage_kv": resolved["base_voltage_kv"],
            "current_scale": resolved["current_scale"],
            "power_scale_mw": resolved["power_scale_mw"],
            "voltage_scale_pu": resolved["voltage_scale_pu"],
            "analysis_window": resolved["analysis_window"],
            "prefault_window": resolved["prefault_window"],
            "fault_window": resolved["fault_window"],
            "postfault_window": resolved["postfault_window"],
            "min_samples": resolved["min_samples"],
        },
        "thevenin": {
            "enabled": resolved["thevenin"]["enabled"],
            "input": resolved["thevenin"],
            "summary": thevenin_summary,
        },
        "summary": {
            "channel_count": len(rows),
            "max_peak_current": max_peak,
            "max_fault_rms_current": max_fault_rms,
            "max_short_circuit_mva": max_scc,
            "min_scr": thevenin_summary.get("min_scr"),
            "min_escr": thevenin_summary.get("min_escr"),
            "worst_grid_strength": thevenin_summary.get("worst_grid_strength"),
            "methods": sorted({row["analysis"]["method"] for row in rows}),
        },
        "channels": rows,
    }

    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "short_circuit_analysis")
    artifacts = _write_artifacts(
        result_data,
        target_dir,
        prefix,
        generate_report=bool(output_config.get("generate_report", True)),
    )
    return {**result_data, "artifacts": artifacts}
