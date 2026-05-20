from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/<your-account>/IEEE3")
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


def make_fault_variant(model, *, fault_end_time: str | None = None, fault_chg: str | None = None):
    working_model = Model(deepcopy(model.toJSON()))
    components = working_model.getAllComponents()
    fault = next((component for component in components.values() if getattr(component, "definition", None) == FAULT_DEFINITION), None)
    if fault is None:
        return working_model, {"variant": "baseline-copy", "reason": "no fault component found"}
    args = deepcopy(fault.args)
    if fault_end_time is not None:
        args["fe"] = {"source": str(fault_end_time), "ɵexp": ""}
    if fault_chg is not None:
        args["chg"] = {"source": str(fault_chg), "ɵexp": ""}
    working_model.updateComponent(fault.id, args=args)
    return working_model, {"variant": "fault-parameter-update", "fault_id": fault.id, "fault_end_time": fault_end_time, "fault_chg": fault_chg}


def extract_channels(result, *, plot_index: int = 2, max_channels: int = 3) -> dict[str, dict[str, list[float]]]:
    plots = list(result.getPlots())
    if not plots:
        raise RuntimeError("No plots in EMT result")
    if plot_index >= len(plots):
        plot_index = 0
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
        raise RuntimeError("No channels extracted for comparison")
    return channels


def metric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise RuntimeError("Cannot compute metrics for empty series")
    mean = sum(values) / len(values)
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    return {
        "max": max(values),
        "min": min(values),
        "mean": mean,
        "rms": rms,
        "peak_to_peak": max(values) - min(values),
    }


def compare_scenarios(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    if len(scenarios) < 2:
        raise ValueError("At least two scenarios are required")
    common_channels = set(scenarios[0]["channels"].keys())
    for scenario in scenarios[1:]:
        common_channels &= set(scenario["channels"].keys())
    if not common_channels:
        raise RuntimeError("No common channels across scenarios")

    comparison: dict[str, Any] = {}
    baseline = scenarios[0]
    for channel in sorted(common_channels):
        channel_comparison: dict[str, Any] = {}
        baseline_metrics = metric_summary(baseline["channels"][channel]["y"])
        for scenario in scenarios:
            metrics = metric_summary(scenario["channels"][channel]["y"])
            deltas = {name: value - baseline_metrics[name] for name, value in metrics.items()}
            channel_comparison[scenario["label"]] = {"metrics": metrics, "delta_vs_baseline": deltas}
        comparison[channel] = channel_comparison
    if not comparison:
        raise RuntimeError("Empty comparison")
    return {
        "scenario_count": len(scenarios),
        "common_channels": sorted(common_channels),
        "comparison": comparison,
    }


def write_outputs(scenarios: list[dict[str, Any]], comparison: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "result_comparison.json"
    json_payload = {
        "scenarios": [
            {"label": scenario["label"], "job_id": scenario["job_id"], "channel_count": len(scenario["channels"])}
            for scenario in scenarios
        ],
        **comparison,
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = output_dir / "result_comparison.md"
    lines = [
        "# CloudPSS EMT Result Comparison",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in scenarios:
        lines.append(f"- {scenario['label']}: `{scenario['job_id']}`")
    lines.extend(["", "## Common Channels", ""])
    for channel in comparison["common_channels"]:
        lines.append(f"- `{channel}`")
    lines.extend(["", "## Metric Deltas", ""])
    for channel, channel_data in comparison["comparison"].items():
        lines.append(f"### {channel}")
        lines.append("")
        lines.append("| Scenario | Max | Min | Mean | RMS | Peak-to-peak |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for label, payload in channel_data.items():
            metrics = payload["metrics"]
            lines.append(
                f"| {label} | {metrics['max']:.6g} | {metrics['min']:.6g} | "
                f"{metrics['mean']:.6g} | {metrics['rms']:.6g} | {metrics['peak_to_peak']:.6g} |"
            )
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    first_channel = comparison["common_channels"][0]
    waveform_path = output_dir / "waveform_overlay.png"
    fig, ax = plt.subplots(figsize=(10, 5))
    for scenario in scenarios:
        data = scenario["channels"][first_channel]
        ax.plot(data["x"], data["y"], label=scenario["label"], linewidth=1.2)
    ax.set_title(f"Waveform overlay: {first_channel}")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Value")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(waveform_path, dpi=140)
    plt.close(fig)

    metric_path = output_dir / "metric_compare.png"
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [scenario["label"] for scenario in scenarios]
    rms_values = [metric_summary(scenario["channels"][first_channel]["y"])["rms"] for scenario in scenarios]
    ax.bar(labels, rms_values)
    ax.set_title(f"RMS comparison: {first_channel}")
    ax.set_ylabel("RMS")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(metric_path, dpi=140)
    plt.close(fig)

    artifacts = [json_path, md_path, waveform_path, metric_path]
    for path in artifacts:
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "charts": [str(waveform_path), str(metric_path)],
    }


def run_live_comparison(model, output_dir: Path, *, timeout: int = 300) -> dict[str, Any]:
    baseline_model = Model(deepcopy(model.toJSON()))
    variant_model, variant_info = make_fault_variant(model, fault_end_time="2.9", fault_chg="0.01")
    baseline_job = run_emt(baseline_model, timeout=timeout)
    variant_job = run_emt(variant_model, timeout=timeout)
    scenarios = [
        {
            "label": "baseline",
            "job_id": getattr(baseline_job, "id", None),
            "channels": extract_channels(baseline_job.result, plot_index=2, max_channels=3),
        },
        {
            "label": "variant",
            "job_id": getattr(variant_job, "id", None),
            "channels": extract_channels(variant_job.result, plot_index=2, max_channels=3),
        },
    ]
    comparison = compare_scenarios(scenarios)
    outputs = write_outputs(scenarios, comparison, output_dir)
    return {
        "variant_info": variant_info,
        "job_ids": [scenario["job_id"] for scenario in scenarios],
        "comparison": comparison,
        "artifacts": outputs,
    }
