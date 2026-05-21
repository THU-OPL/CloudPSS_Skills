from __future__ import annotations

import csv
import json
import logging
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
    "fe_values": [2.70, 2.75, 2.80, 2.85, 2.90],
    "chg": 0.01,
}
DEFAULT_OUTPUT_DIR = Path("results") / "skill-verification" / "fault-clearing-scan"


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


def _trace_value_at_time(trace: dict[str, Any], target_time: float, tolerance: float = 0.001) -> float:
    for time_value, value in zip(trace["x"], trace["y"]):
        if abs(time_value - target_time) < tolerance:
            return float(value)
    raise ValueError(f"在 {target_time}s 附近未找到目标通道采样点")


def _resolve_scan_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    scan = config.get("scan", {})
    assessment = config.get("assessment", {})
    dimensions = config.get("scenario_dimensions", {})
    output = config.get("output", {})
    return {
        "fs": scan.get("fs", dimensions.get("fs", DEFAULT_SCAN["fs"])),
        "fe_values": list(scan.get("fe_values", dimensions.get("fe_values", DEFAULT_SCAN["fe_values"]))),
        "chg": scan.get("chg", dimensions.get("chg", DEFAULT_SCAN["chg"])),
        "trace_name": assessment.get("trace_name", dimensions.get("trace_name", DEFAULT_TRACE_NAME)),
        "study_time": assessment.get("study_time", 2.95),
        "sampling_freq": int(assessment.get("sampling_freq", 2000)),
        "fault_point": config.get("fault_point", {}),
        "breaker_action": config.get("breaker_action", {}),
        "output": output,
    }


def run_fault_clearing_scan(model, config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    scan_config = _resolve_scan_config(config)
    fe_values = scan_config["fe_values"]
    if not fe_values:
        raise ValueError("fe_values 不能为空")

    results: list[dict[str, Any]] = []
    for fe in fe_values:
        working_model = _clone_model(model)
        _apply_fault_parameters(
            working_model,
            fs=scan_config["fs"],
            fe=fe,
            chg=scan_config["chg"],
            trace_name=scan_config["trace_name"],
            sampling_freq=scan_config["sampling_freq"],
        )
        job = _run_emt(working_model)
        _, trace = _find_trace(job.result, scan_config["trace_name"])
        voltage_at_study = _trace_value_at_time(trace, scan_config["study_time"])
        results.append(
            {
                "fe": fe,
                "voltage_at_study": voltage_at_study,
                "job_id": job.id,
            }
        )

    results_sorted = sorted(results, key=lambda item: item["fe"])
    monotonic_degradation = all(
        results_sorted[index]["voltage_at_study"] >= results_sorted[index + 1]["voltage_at_study"]
        for index in range(len(results_sorted) - 1)
    )

    output_config = scan_config["output"]
    target_dir = Path(output_dir or output_config.get("path", DEFAULT_OUTPUT_DIR))
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_config.get("prefix", "fault_clearing_scan")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    result_data = {
        "model": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "fault_point": scan_config["fault_point"],
        "breaker_action": scan_config["breaker_action"],
        "scan": {
            "fs": scan_config["fs"],
            "fe_values": fe_values,
            "chg": scan_config["chg"],
        },
        "assessment": {
            "trace_name": scan_config["trace_name"],
            "study_time": scan_config["study_time"],
        },
        "monotonic_degradation": monotonic_degradation,
        "results": results_sorted,
    }

    json_path = target_dir / f"{prefix}_{timestamp}.json"
    json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = target_dir / f"{prefix}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["fe", "voltage_at_study", "job_id"])
        for row in results_sorted:
            writer.writerow([row["fe"], f"{row['voltage_at_study']:.6f}", row["job_id"]])

    markdown_path = target_dir / f"{prefix}_report_{timestamp}.md"
    if output_config.get("generate_report", True):
        lines = [
            "# Fault Clearing Scan Report",
            "",
            f"- Model: `{result_data['model']}`",
            f"- RID: `{result_data['model_rid']}`",
            f"- Study time: `{scan_config['study_time']}s`",
            f"- Trace: `{scan_config['trace_name']}`",
            f"- Monotonic degradation: `{monotonic_degradation}`",
            "",
            "| fe | voltage_at_study | job_id |",
            "| --- | ---: | --- |",
        ]
        for row in results_sorted:
            lines.append(f"| {row['fe']} | {row['voltage_at_study']:.6f} | {row['job_id']} |")
        lines.append("")
        if monotonic_degradation:
            lines.append("**Conclusion**: Later clearing produces a lower voltage at the study time.")
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
