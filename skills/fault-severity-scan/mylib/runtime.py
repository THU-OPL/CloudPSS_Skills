from __future__ import annotations

import csv
import json
import logging
import math
import os
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from cloudpss import Model, setToken


logger = logging.getLogger(__name__)

DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/<your-account>/IEEE3")
FAULT_DEFINITION = "model/CloudPSS/_newFaultResistor_3p"
CHANNEL_DEFINITION = "model/CloudPSS/_newChannel"
EMT_JOB_RID = "function/CloudPSS/emtps"
DEFAULT_TRACE_NAME = "vac:0"
DEFAULT_SCAN = {
    "fs": 2.5,
    "fe": 2.7,
    "chg_values": [0.01, 0.1, 1.0, 10.0, 100.0],
}
DEFAULT_TIME_WINDOWS = {
    "prefault": [2.42, 2.44],
    "fault": [2.56, 2.58],
    "postfault": [2.92, 2.94],
}
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "fault-severity-scan"


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


def _clone_model(base_model):
    return Model(deepcopy(base_model.toJSON()))


def _find_fault_component(model):
    for component in model.getAllComponents().values():
        if getattr(component, "definition", None) == FAULT_DEFINITION:
            return component
    raise ValueError("未找到故障元件")


def _trace_channel_name(trace_name: str) -> str:
    return (trace_name or DEFAULT_TRACE_NAME).split(":", 1)[0]


def _find_measurement_channel(model, trace_name: str):
    channel_name = _trace_channel_name(trace_name)
    for component in model.getAllComponents().values():
        if getattr(component, "definition", None) == CHANNEL_DEFINITION and component.args.get("Name") == channel_name:
            return component
    raise ValueError(f"未找到量测通道: {channel_name}")


def _find_emt_job(model):
    for job in getattr(model, "jobs", []):
        if job.get("rid") == EMT_JOB_RID:
            return job
    raise ValueError("未找到EMT任务")


def _find_output_group(emt_job, channel_id):
    output_channels = emt_job.get("args", {}).get("output_channels", [])
    for index, group in enumerate(output_channels):
        if channel_id in group.get("4", []):
            return index, group
    raise KeyError(f"未找到包含通道 {channel_id} 的EMT输出分组")


def _apply_fault_parameters(model, *, fs: float, fe: float, chg: float, trace_name: str, sampling_freq: int):
    fault = _find_fault_component(model)
    channel = _find_measurement_channel(model, trace_name)
    emt_job = _find_emt_job(model)
    _, output_group = _find_output_group(emt_job, channel.id)

    model.updateComponent(
        fault.id,
        args={
            "fs": {"source": str(fs), "ɵexp": ""},
            "fe": {"source": str(fe), "ɵexp": ""},
            "chg": {"source": str(chg), "ɵexp": ""},
        },
    )
    model.updateComponent(
        channel.id,
        args={**channel.args, "Freq": {"source": str(sampling_freq), "ɵexp": ""}},
    )
    output_group["1"] = int(sampling_freq)
    return model


def _wait_for_completion(job, timeout: int = 300, poll_seconds: int = 3):
    start_time = time.time()
    while True:
        status = job.status()
        if status == 1:
            return job
        if status == 2:
            raise RuntimeError("EMT仿真失败")
        if time.time() - start_time > timeout:
            raise TimeoutError("EMT仿真超时")
        time.sleep(poll_seconds)


def _run_emt(model, *, timeout: int = 300):
    job = model.runEMT()
    return _wait_for_completion(job, timeout=timeout)


def _find_trace(result, trace_name: str):
    for plot_index, _plot in enumerate(result.getPlots()):
        channel_names = result.getPlotChannelNames(plot_index)
        if trace_name in channel_names:
            return plot_index, result.getPlotChannelData(plot_index, trace_name)
    raise KeyError(f"未找到目标通道 {trace_name}")


def _trace_rms(trace: dict[str, Any], start_time: float, end_time: float) -> float:
    samples = [
        float(value)
        for time_value, value in zip(trace["x"], trace["y"])
        if start_time <= time_value <= end_time
    ]
    if not samples:
        raise ValueError(f"时间窗口 {start_time}..{end_time} 内无数据")
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def _resolve_time_windows(raw_windows: dict[str, Any] | None) -> dict[str, list[float]]:
    windows = dict(DEFAULT_TIME_WINDOWS)
    for name, value in (raw_windows or {}).items():
        if name not in windows:
            continue
        if not isinstance(value, list | tuple) or len(value) != 2:
            raise ValueError(f"time_windows.{name} must be [start, end]")
        windows[name] = [float(value[0]), float(value[1])]
    return windows


def _resolve_scan_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    scan = config.get("scan", {})
    assessment = config.get("assessment", {})
    dimensions = config.get("scenario_dimensions", {})
    output = config.get("output", {})
    return {
        "fs": scan.get("fs", dimensions.get("fs", DEFAULT_SCAN["fs"])),
        "fe": scan.get("fe", dimensions.get("fe", DEFAULT_SCAN["fe"])),
        "chg_values": list(scan.get("chg_values", dimensions.get("chg_values", DEFAULT_SCAN["chg_values"]))),
        "trace_name": assessment.get("trace_name", dimensions.get("trace_name", DEFAULT_TRACE_NAME)),
        "time_windows": _resolve_time_windows(assessment.get("time_windows")),
        "sampling_freq": int(assessment.get("sampling_freq", 2000)),
        "fault_point": config.get("fault_point", {}),
        "breaker_action": config.get("breaker_action", {}),
        "output": output,
    }


def _extract_metrics(trace: dict[str, Any], time_windows: dict[str, list[float]]) -> dict[str, float]:
    prefault_rms = _trace_rms(trace, *time_windows["prefault"])
    fault_rms = _trace_rms(trace, *time_windows["fault"])
    postfault_rms = _trace_rms(trace, *time_windows["postfault"])
    return {
        "prefault_rms": prefault_rms,
        "fault_rms": fault_rms,
        "postfault_rms": postfault_rms,
        "fault_drop": prefault_rms - fault_rms,
        "postfault_gap": prefault_rms - postfault_rms,
    }


def run_fault_severity_scan(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    scan_config = _resolve_scan_config(config)
    chg_values = scan_config["chg_values"]
    if not chg_values:
        raise ValueError("chg_values 不能为空")

    results: list[dict[str, Any]] = []
    for chg in chg_values:
        working_model = _clone_model(model)
        _apply_fault_parameters(
            working_model,
            fs=scan_config["fs"],
            fe=scan_config["fe"],
            chg=chg,
            trace_name=scan_config["trace_name"],
            sampling_freq=scan_config["sampling_freq"],
        )
        job = _run_emt(working_model)
        _, trace = _find_trace(job.result, scan_config["trace_name"])
        metrics = _extract_metrics(trace, scan_config["time_windows"])
        results.append(
            {
                "chg": chg,
                **metrics,
                "job_id": job.id,
            }
        )

    results_sorted = sorted(results, key=lambda item: item["chg"])
    fault_drops = [row["fault_drop"] for row in results_sorted]
    postfault_gaps = [row["postfault_gap"] for row in results_sorted]
    fault_trend = (
        "decreasing"
        if all(fault_drops[index] >= fault_drops[index + 1] for index in range(len(fault_drops) - 1))
        else "mixed"
    )
    gap_trend = (
        "decreasing"
        if all(postfault_gaps[index] >= postfault_gaps[index + 1] for index in range(len(postfault_gaps) - 1))
        else "mixed"
    )

    output_config = scan_config["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_config.get("prefix", "fault_severity_scan")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "fault_point": scan_config["fault_point"],
        "breaker_action": scan_config["breaker_action"],
        "scan": {
            "fs": scan_config["fs"],
            "fe": scan_config["fe"],
            "chg_values": chg_values,
        },
        "assessment": {
            "trace_name": scan_config["trace_name"],
            "time_windows": scan_config["time_windows"],
        },
        "fault_trend": fault_trend,
        "gap_trend": gap_trend,
        "results": results_sorted,
    }

    json_path = target_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = target_dir / f"{prefix}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["chg", "prefault_rms", "fault_rms", "postfault_rms", "fault_drop", "postfault_gap", "job_id"])
        for row in results_sorted:
            writer.writerow(
                [
                    row["chg"],
                    f"{row['prefault_rms']:.6f}",
                    f"{row['fault_rms']:.6f}",
                    f"{row['postfault_rms']:.6f}",
                    f"{row['fault_drop']:.6f}",
                    f"{row['postfault_gap']:.6f}",
                    row["job_id"],
                ]
            )

    markdown_path = target_dir / f"{prefix}_report_{timestamp}.md"
    if output_config.get("generate_report", True):
        lines = [
            "# Fault Severity Scan Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Trace: `{scan_config['trace_name']}`",
            f"- Fault trend: `{fault_trend}`",
            f"- Gap trend: `{gap_trend}`",
            "",
            "| chg | prefault_rms | fault_rms | postfault_rms | fault_drop | postfault_gap | job_id |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for row in results_sorted:
            lines.append(
                f"| {row['chg']} | {row['prefault_rms']:.6f} | {row['fault_rms']:.6f} | "
                f"{row['postfault_rms']:.6f} | {row['fault_drop']:.6f} | {row['postfault_gap']:.6f} | {row['job_id']} |"
            )
        lines.append("")
        if fault_trend == "decreasing" and gap_trend == "decreasing":
            lines.append("**Conclusion**: Larger fault resistance corresponds to milder voltage drop and smaller recovery gap.")
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        markdown_path = None

    return {
        **result_data,
        "artifacts": {
            "json_path": str(json_path),
            "csv_path": str(csv_path),
            "markdown_path": str(markdown_path) if markdown_path else "",
        },
    }
