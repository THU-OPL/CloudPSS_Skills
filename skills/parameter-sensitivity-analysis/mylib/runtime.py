from __future__ import annotations

import csv
import json
import math
import os
import re
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/CloudPSS/IEEE3")
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "parameter-sensitivity-analysis"


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


def _clone_model(model):
    return Model(deepcopy(model.toJSON()))


def _resolve_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    scan = config.get("scan", {})
    metrics = config.get("metrics", {})
    output = config.get("output", {})
    target = scan.get("target", {})
    if isinstance(target, str):
        if "." not in target:
            raise ValueError("String scan.target must use Component.arg format")
        component, arg = target.rsplit(".", 1)
        target = {"component": component, "arg": arg}
    values = list(scan.get("values", []))
    if len(values) < 2:
        raise ValueError("scan.values must contain at least two values")
    return {
        "target": {
            "component": str(target.get("component", "")),
            "arg": str(target.get("arg", "")),
        },
        "values": [float(value) for value in values],
        "reference": float(scan.get("reference", values[len(values) // 2])),
        "simulation_type": scan.get("simulation_type", "emt"),
        "timeout": int(scan.get("timeout", 300)),
        "channels": list(metrics.get("channels", [])),
        "auto_max_channels": int(metrics.get("auto_max_channels", 6)),
        "time_window": metrics.get("time_window"),
        "metric_names": list(metrics.get("metric_names", ["mean", "rms", "min", "max", "peak_to_peak", "final"])),
        "min_samples": int(metrics.get("min_samples", 128)),
        "output": output,
    }


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _component_matches(key: str, comp: Any, target: str) -> bool:
    target_norm = _normalize_identifier(target)
    candidates = [
        key,
        getattr(comp, "label", ""),
        getattr(comp, "name", ""),
    ]
    args = getattr(comp, "args", {}) or {}
    name_arg = args.get("Name", "")
    if isinstance(name_arg, dict):
        candidates.append(name_arg.get("source", ""))
    else:
        candidates.append(str(name_arg))
    return any(_normalize_identifier(candidate) == target_norm for candidate in candidates)


def _find_component_key(model, component_selector: str) -> str:
    components = model.getAllComponents()
    for key, comp in components.items():
        if not hasattr(comp, "args"):
            continue
        if _component_matches(key, comp, component_selector):
            return key
    raise KeyError(f"Component not found: {component_selector}")


def _get_arg_source(model, component_key: str, arg_name: str) -> str | None:
    comp = model.getAllComponents()[component_key]
    args = getattr(comp, "args", {}) or {}
    value = args.get(arg_name)
    if isinstance(value, dict):
        source = value.get("source")
        return None if source is None else str(source)
    if value is None:
        return None
    return str(value)


def _apply_parameter(model, component_key: str, arg_name: str, value: float) -> None:
    model.updateComponent(component_key, args={arg_name: {"source": f"{value:.12g}", "ɵexp": ""}})


def _plot_name(plot: dict[str, Any], index: int) -> str:
    return plot.get("key") or plot.get("name") or f"plot_{index}"


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


def _auto_channel_names(result, max_channels: int) -> list[str]:
    selected: list[str] = []
    preferred_tokens = ("#p", "#wr", "vac")
    for token in preferred_tokens:
        for plot_index, _plot in enumerate(result.getPlots()):
            for channel_name in result.getPlotChannelNames(plot_index):
                if len(selected) >= max_channels:
                    return selected
                if token in channel_name.lower() and channel_name not in selected:
                    selected.append(channel_name)
    if selected:
        return selected
    for plot_index, _plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            if len(selected) >= max_channels:
                return selected
            if channel_name not in selected:
                selected.append(channel_name)
    return selected


def _window_values(trace: dict[str, list[float]], window: list[float] | tuple[float, float] | None) -> tuple[list[float], list[float]]:
    x_values = trace["x"]
    y_values = trace["y"]
    if any(x_values[index] >= x_values[index + 1] for index in range(len(x_values) - 1)):
        raise ValueError("Waveform time axis is not strictly increasing")
    if window:
        if len(window) != 2:
            raise ValueError("time_window must be [start, end]")
        start = float(window[0])
        end = float(window[1])
    else:
        start = x_values[0]
        end = x_values[-1]
    out_x: list[float] = []
    out_y: list[float] = []
    for x_value, y_value in zip(x_values, y_values):
        if start <= x_value <= end:
            out_x.append(x_value)
            out_y.append(y_value)
    return out_x, out_y


def _metric_summary(trace: dict[str, list[float]], *, time_window: list[float] | tuple[float, float] | None, metric_names: list[str], min_samples: int) -> dict[str, float]:
    x_values, values = _window_values(trace, time_window)
    if len(values) < min_samples:
        raise ValueError(f"Not enough samples in metric window: {len(values)} < {min_samples}")
    mean = sum(values) / len(values)
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    min_value = min(values)
    max_value = max(values)
    all_metrics = {
        "mean": mean,
        "rms": rms,
        "min": min_value,
        "max": max_value,
        "peak_to_peak": max_value - min_value,
        "final": values[-1],
        "abs_max": max(abs(value) for value in values),
        "sample_count": float(len(values)),
        "t_start": x_values[0],
        "t_end": x_values[-1],
    }
    return {name: all_metrics[name] for name in metric_names if name in all_metrics}


def _extract_metrics(result, channels: list[str], *, auto_max_channels: int, time_window: list[float] | tuple[float, float] | None, metric_names: list[str], min_samples: int) -> dict[str, float]:
    channel_names = channels or _auto_channel_names(result, auto_max_channels)
    metrics: dict[str, float] = {}
    for channel_name in channel_names:
        _plot_index, _plot, trace = _find_trace(result, channel_name)
        summary = _metric_summary(trace, time_window=time_window, metric_names=metric_names, min_samples=min_samples)
        for metric_name, metric_value in summary.items():
            metrics[f"{channel_name}.{metric_name}"] = metric_value
    if not metrics:
        raise RuntimeError("No metrics extracted")
    return metrics


def _linear_sensitivity(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((x_value - x_mean) ** 2 for x_value in x_values)
    if abs(denominator) <= 1e-18:
        return 0.0
    numerator = sum((x_value - x_mean) * (y_value - y_mean) for x_value, y_value in points)
    return numerator / denominator


def _calculate_sensitivities(results: list[dict[str, Any]], target_name: str, reference: float) -> list[dict[str, Any]]:
    metric_names: set[str] = set()
    for row in results:
        metric_names.update(row["metrics"].keys())
    sensitivities: list[dict[str, Any]] = []
    for metric_name in metric_names:
        points = [(row["parameter_value"], row["metrics"][metric_name]) for row in results if metric_name in row["metrics"]]
        points.sort(key=lambda item: item[0])
        sensitivity = _linear_sensitivity(points)
        y_mean = sum(value for _x, value in points) / len(points) if points else 0.0
        normalized = sensitivity * reference / y_mean if abs(reference) > 1e-18 and abs(y_mean) > 1e-18 else sensitivity
        if points:
            sensitivities.append(
                {
                    "parameter": target_name,
                    "metric": metric_name,
                    "sensitivity": sensitivity,
                    "normalized_sensitivity": normalized,
                    "metric_mean": y_mean,
                    "min_metric": min(value for _x, value in points),
                    "max_metric": max(value for _x, value in points),
                    "rank": 0,
                }
            )
    sensitivities.sort(key=lambda item: abs(item["normalized_sensitivity"]), reverse=True)
    for index, item in enumerate(sensitivities):
        item["rank"] = index + 1
    return sensitivities


def _write_artifacts(result_data: dict[str, Any], output_dir: Path, prefix: str, *, generate_report: bool) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / f"{prefix}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["rank", "parameter", "metric", "sensitivity", "normalized_sensitivity", "metric_mean", "min_metric", "max_metric"])
        for row in result_data["sensitivity_ranking"]:
            writer.writerow(
                [
                    row["rank"],
                    row["parameter"],
                    row["metric"],
                    f"{row['sensitivity']:.9g}",
                    f"{row['normalized_sensitivity']:.9g}",
                    f"{row['metric_mean']:.9g}",
                    f"{row['min_metric']:.9g}",
                    f"{row['max_metric']:.9g}",
                ]
            )

    scan_csv_path = output_dir / f"{prefix}_scan_points_{timestamp}.csv"
    metric_order = sorted({metric for row in result_data["scan_results"] for metric in row["metrics"].keys()})
    with scan_csv_path.open("w", newline="", encoding="utf-8") as scan_file:
        writer = csv.writer(scan_file)
        writer.writerow(["parameter_value", "job_id", *metric_order])
        for row in result_data["scan_results"]:
            writer.writerow([row["parameter_value"], row["job_id"], *[row["metrics"].get(metric, "") for metric in metric_order]])

    markdown_path = output_dir / f"{prefix}_report_{timestamp}.md"
    if generate_report:
        lines = [
            "# Parameter Sensitivity Analysis Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Target parameter: `{result_data['target_parameter']}`",
            f"- Reference value: `{result_data['reference_value']}`",
            f"- Simulation type: `{result_data['simulation_type']}`",
            f"- Successful scan points: `{result_data['summary']['successful_points']}`",
            f"- Failed scan points: `{result_data['summary']['failed_points']}`",
            f"- Metrics analyzed: `{result_data['summary']['metric_count']}`",
            "",
            "## Sensitivity Ranking",
            "",
            "| rank | metric | sensitivity | normalized sensitivity |",
            "| ---: | --- | ---: | ---: |",
        ]
        for item in result_data["sensitivity_ranking"][:20]:
            lines.append(
                f"| {item['rank']} | `{item['metric']}` | {item['sensitivity']:.9g} | {item['normalized_sensitivity']:.9g} |"
            )
        lines.extend(
            [
                "",
                "## Scan Points",
                "",
                "| parameter | job id |",
                "| ---: | --- |",
            ]
        )
        for row in result_data["scan_results"]:
            lines.append(f"| {row['parameter_value']:.9g} | `{row['job_id']}` |")
        lines.extend(
            [
                "",
                "## Engineering Notes",
                "",
                "- Sensitivity is estimated by linear regression across the successful scan points.",
                "- Normalized sensitivity uses `dy/dx * reference / mean(metric)` when both denominators are non-zero.",
                "- This skill modifies only local working copies created from the source model; it does not save changes back to CloudPSS.",
            ]
        )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = Path("")

    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "scan_csv_path": str(scan_csv_path),
        "markdown_path": str(markdown_path) if markdown_path else "",
    }


def run_parameter_sensitivity_analysis(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    resolved = _resolve_config(config)
    if resolved["simulation_type"] != "emt":
        raise ValueError("This independent skill currently supports simulation_type='emt' only")

    target_component = resolved["target"]["component"]
    target_arg = resolved["target"]["arg"]
    if not target_component or not target_arg:
        raise ValueError("scan.target requires component and arg")
    base_component_key = _find_component_key(model, target_component)
    original_source = _get_arg_source(model, base_component_key, target_arg)
    target_name = f"{target_component}.{target_arg}"

    scan_results: list[dict[str, Any]] = []
    failed_points: list[dict[str, Any]] = []
    for value in resolved["values"]:
        working_model = _clone_model(model)
        try:
            component_key = _find_component_key(working_model, target_component)
            _apply_parameter(working_model, component_key, target_arg, value)
            job = run_emt(working_model, timeout=resolved["timeout"])
            metrics = _extract_metrics(
                job.result,
                resolved["channels"],
                auto_max_channels=resolved["auto_max_channels"],
                time_window=resolved["time_window"],
                metric_names=resolved["metric_names"],
                min_samples=resolved["min_samples"],
            )
            scan_results.append(
                {
                    "parameter_value": value,
                    "job_id": getattr(job, "id", None),
                    "metrics": metrics,
                }
            )
        except (RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
            failed_points.append({"parameter_value": value, "error": str(exc)})

    if len(scan_results) < 2:
        raise RuntimeError(f"Need at least 2 successful scan points, got {len(scan_results)}; failures={failed_points}")

    sensitivities = _calculate_sensitivities(scan_results, target_name, resolved["reference"])
    if not sensitivities:
        raise RuntimeError("No sensitivities calculated")

    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "target_parameter": target_name,
        "target_component_key": base_component_key,
        "target_original_source": original_source,
        "reference_value": resolved["reference"],
        "scan_values": resolved["values"],
        "simulation_type": resolved["simulation_type"],
        "summary": {
            "successful_points": len(scan_results),
            "failed_points": len(failed_points),
            "metric_count": len({metric for row in scan_results for metric in row["metrics"].keys()}),
            "top_metric": sensitivities[0]["metric"],
            "top_normalized_sensitivity": sensitivities[0]["normalized_sensitivity"],
        },
        "sensitivity_ranking": sensitivities,
        "scan_results": scan_results,
        "failed_points": failed_points,
    }

    output_config = resolved["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    prefix = output_config.get("prefix", "parameter_sensitivity_analysis")
    artifacts = _write_artifacts(
        result_data,
        target_dir,
        prefix,
        generate_report=bool(output_config.get("generate_report", True)),
    )
    return {**result_data, "artifacts": artifacts}
