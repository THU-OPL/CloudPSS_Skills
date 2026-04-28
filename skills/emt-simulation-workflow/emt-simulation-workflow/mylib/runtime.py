from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Any

from cloudpss import Model, setToken


DEFAULT_EMT_MODEL_RID = os.environ.get("TEST_MODEL_RID", "model/holdme/IEEE3")


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
    search_roots = [Path.cwd(), *script_path.parents]
    for root in search_roots:
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


def load_model_from_source(source: str):
    candidate = Path(source).expanduser()
    if candidate.exists():
        return Model.load(str(candidate))
    return Model.fetch(source)


def inspect_emt_topology(model) -> dict[str, Any]:
    topology = model.fetchTopology(implementType="emtp")
    if topology is None:
        raise ValueError(
            f"Model {getattr(model, 'rid', '<unknown>')} is not EMT-ready: "
            "fetchTopology(implementType='emtp') returned no topology."
        )
    topology_data = topology.toJSON()
    return {
        "component_count": len(topology_data.get("components", {})),
        "mapping_key_preview": list(topology_data.get("mappings", {}).keys())[:5],
    }


def wait_for_completion(job, timeout: int = 300, interval: int = 3) -> int:
    start_time = time.time()
    while True:
        status = job.status()
        if status in {1, 2}:
            return status
        if time.time() - start_time > timeout:
            return -1
        time.sleep(interval)


def describe_plot(plot: dict[str, Any], index: int) -> str:
    return plot.get("key") or plot.get("name") or f"plot_{index}"


def collect_plot_summaries(result) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, plot in enumerate(result.getPlots()):
        channel_names = result.getPlotChannelNames(index)
        summaries.append(
            {
                "index": index,
                "plot": describe_plot(plot, index),
                "channel_count": len(channel_names),
                "channel_preview": channel_names[:10],
            }
        )
    return summaries


def export_first_channel_csv(result, plot_index: int, channel_name: str, output_path: Path) -> Path:
    channel_data = result.getPlotChannelData(plot_index, channel_name)
    if not channel_data:
        raise ValueError(f"Channel data not found: plot_index={plot_index}, channel={channel_name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["time", "value"])
        for x_value, y_value in zip(channel_data.get("x", []), channel_data.get("y", [])):
            writer.writerow([x_value, y_value])
    return output_path


def run_emt_workflow(model, *, timeout: int = 300, export_dir: Path | None = None) -> dict[str, Any]:
    topology_summary = inspect_emt_topology(model)
    job = model.runEMT()
    final_status = wait_for_completion(job, timeout=timeout)
    if final_status == -1:
        raise TimeoutError("EMT job timed out")
    if final_status == 2:
        raise RuntimeError("EMT job failed")

    result = job.result
    if result is None:
        raise RuntimeError("EMT result is empty")

    plot_summaries = collect_plot_summaries(result)
    exported_files: list[str] = []
    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        for plot_summary in plot_summaries:
            preview = plot_summary["channel_preview"]
            if not preview:
                continue
            first_channel = preview[0]
            output_path = export_dir / f"plot_{plot_summary['index']}_{first_channel.replace(':', '_')}.csv"
            exported_files.append(str(export_first_channel_csv(result, plot_summary["index"], first_channel, output_path)))

    return {
        "job_id": getattr(job, "id", None),
        "status": final_status,
        "topology": topology_summary,
        "plot_count": len(plot_summaries),
        "plots": plot_summaries,
        "artifacts": exported_files,
    }
