from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import time
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/<your-account>/IEEE3")
CHANNEL_DEFINITION = "model/CloudPSS/_newChannel"
EMT_JOB_RID = "function/CloudPSS/emtps"


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


def find_emt_job(model) -> dict[str, Any]:
    for job in model.jobs:
        if job.get("rid") == EMT_JOB_RID:
            return job
    for job in model.jobs:
        if "暂态" in str(job.get("name", "")) or "EMT" in str(job.get("name", "")).upper():
            return job
    raise KeyError("No EMT job found")


def _arg_source(value: Any, default: str = "") -> str:
    if isinstance(value, dict):
        return str(value.get("source", default))
    if value is None:
        return default
    return str(value)


def _arg_int(value: Any, default: int) -> int:
    try:
        return int(float(_arg_source(value, str(default))))
    except (TypeError, ValueError):
        return default


def channel_components(model) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for component in model.getAllComponents().values():
        if getattr(component, "definition", None) != CHANNEL_DEFINITION:
            continue
        args = getattr(component, "args", {}) or {}
        rows.append(
            {
                "id": component.id,
                "label": getattr(component, "label", ""),
                "name": _arg_source(args.get("Name"), component.id),
                "dimension": _arg_int(args.get("Dim"), 1),
                "frequency_hz": _arg_int(args.get("Freq"), 1000),
            }
        )
    return rows


def output_groups(model) -> list[dict[str, Any]]:
    emt_job = find_emt_job(model)
    groups = emt_job.get("args", {}).get("output_channels", []) or []
    return [
        {
            "index": index,
            "name": group.get("0", ""),
            "frequency_hz": group.get("1"),
            "storage": group.get("2"),
            "enabled": group.get("3"),
            "channel_ids": list(group.get("4", []) or []),
        }
        for index, group in enumerate(groups)
    ]


def analyze_channel_setup(model) -> dict[str, Any]:
    channels = channel_components(model)
    groups = output_groups(model)
    mapped = {channel_id for group in groups for channel_id in group["channel_ids"]}
    return {
        "model_rid": getattr(model, "rid", ""),
        "model_name": getattr(model, "name", ""),
        "emt_job_name": find_emt_job(model).get("name", ""),
        "channel_count": len(channels),
        "channels": channels,
        "output_group_count": len(groups),
        "output_groups": groups,
        "unmapped_channel_ids": [channel["id"] for channel in channels if channel["id"] not in mapped],
    }


def configure_working_copy_output_group(model, selected_channel_ids: list[str], *, group_name: str, frequency_hz: int):
    working_model = Model(deepcopy(model.toJSON()))
    emt_job = find_emt_job(working_model)
    existing_groups = emt_job.setdefault("args", {}).setdefault("output_channels", [])
    template = deepcopy(existing_groups[0]) if existing_groups else {}
    template.update(
        {
            "0": group_name,
            "1": int(frequency_hz),
            "2": template.get("2", "compressed"),
            "3": 1,
            "4": list(selected_channel_ids),
        }
    )
    emt_job["args"]["output_channels"] = [template]
    return working_model


def collect_plot_summaries(result) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, plot in enumerate(result.getPlots()):
        names = result.getPlotChannelNames(index)
        summaries.append(
            {
                "index": index,
                "plot": plot.get("key") or plot.get("name") or f"plot_{index}",
                "channel_count": len(names),
                "channel_preview": names[:10],
            }
        )
    return summaries


def run_configured_channel_validation(model, *, max_channels: int = 3, frequency_hz: int = 1000, timeout: int = 300) -> dict[str, Any]:
    baseline = analyze_channel_setup(model)
    if baseline["channel_count"] == 0:
        raise RuntimeError("No _newChannel components found")
    selected = baseline["channels"][:max_channels]
    selected_ids = [channel["id"] for channel in selected]
    selected_names = [channel["name"] for channel in selected]
    selected_base_names = {name.split(":", 1)[0] for name in selected_names}
    working_model = configure_working_copy_output_group(
        model,
        selected_ids,
        group_name="auto-channel-setup-validation",
        frequency_hz=frequency_hz,
    )
    job = working_model.runEMT()
    final_status = wait_for_completion(job, timeout=timeout)
    if final_status == -1:
        raise TimeoutError("EMT job timed out")
    if final_status == 2:
        raise RuntimeError("EMT job failed")
    result = job.result
    if result is None:
        raise RuntimeError("EMT result is empty")

    plot_summaries = collect_plot_summaries(result)
    target_channel_points: dict[str, int] = {}
    for plot_index, _plot in enumerate(result.getPlots()):
        for channel_name in result.getPlotChannelNames(plot_index):
            base_name = channel_name.split(":", 1)[0]
            if base_name not in selected_base_names:
                continue
            data = result.getPlotChannelData(plot_index, channel_name)
            if data:
                target_channel_points[channel_name] = len(data.get("x", []))

    if not target_channel_points:
        raise RuntimeError(f"None of the selected channels appeared in EMT result: {selected_names}")
    if min(target_channel_points.values()) <= 0:
        raise RuntimeError(f"Selected channel has no samples: {target_channel_points}")

    return {
        "baseline": baseline,
        "configured_group": {
            "name": "auto-channel-setup-validation",
            "frequency_hz": frequency_hz,
            "selected_channel_ids": selected_ids,
            "selected_channel_names": selected_names,
        },
        "job_id": getattr(job, "id", None),
        "status": final_status,
        "plots": plot_summaries,
        "target_channel_points": target_channel_points,
    }
