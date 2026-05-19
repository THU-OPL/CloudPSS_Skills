from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

for env_path in [ROOT / ".env", *[parent / ".env" for parent in ROOT.parents]]:
    if env_path.exists():
        load_dotenv(env_path)
        break

from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402


MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/yuanxuefeng/IEEE39")
PF_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
EMT_JOB_NAME = os.environ.get("CLOUDPSS_TEST_EMT_JOB", "电磁暂态仿真方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")
MIN_BUS_COUNT = int(os.environ.get("CLOUDPSS_TEST_MIN_BUS_COUNT", "39"))
BUS_RID = "model/CloudPSS/_newBus_3p"
GEN_RID = "model/CloudPSS/SyncGeneratorRouter"
LINE_RID = "model/CloudPSS/TransmissionLine"


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def build_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=MODEL_ID)
    log(f"init-done result={result}")
    return sa


def get_component_cells(revision: dict[str, Any]) -> list[dict[str, Any]]:
    cells = revision["implements"]["diagram"]["cells"]
    return [
        {"id": key, **value}
        for key, value in cells.items()
        if isinstance(value, dict) and "definition" in value and "shape" in value
    ]


def unique_labels(cells: list[dict[str, Any]], *, definition: str | None = None, label_contains: str | None = None) -> list[str]:
    labels: list[str] = []
    for cell in cells:
        if definition and cell.get("definition") != definition:
            continue
        label = cell.get("label")
        if not isinstance(label, str) or not label:
            continue
        if label_contains and label_contains not in label:
            continue
        if label not in labels:
            labels.append(label)
    return labels


def summarize_revision(revision: dict[str, Any]) -> dict[str, Any]:
    cells = get_component_cells(revision)
    bus_labels = unique_labels(cells, definition=BUS_RID)
    gen_labels = unique_labels(cells, definition=GEN_RID)
    line_labels = unique_labels(cells, definition=LINE_RID)
    if not line_labels:
        line_labels = unique_labels(cells, label_contains="TLine_3p-")
    return {
        "component_count": len(cells),
        "bus_count": len(bus_labels),
        "generator_count": len(gen_labels),
        "line_label_count": len(line_labels),
        "sample_bus_labels": bus_labels[:5],
        "sample_generator_labels": gen_labels[:5],
        "sample_line_labels": line_labels[:5],
    }


def scenario_inventory() -> dict[str, Any]:
    log("scenario inventory start")
    sa = build_case()
    pf_job = sa.getCurrentJob(stype="power-flow", jobName=PF_JOB_NAME)
    emt_job = sa.getCurrentJob(stype="emtps", jobName=EMT_JOB_NAME)
    config = sa.getCurrentConfig(configName=CONFIG_NAME)
    revision = sa.getRevision()
    inventory = summarize_revision(revision)

    if not pf_job:
        raise RuntimeError("Power-flow job not found")
    if not emt_job:
        raise RuntimeError("EMT job not found")
    if not config:
        raise RuntimeError("Config not found")
    if inventory["bus_count"] < MIN_BUS_COUNT:
        raise RuntimeError(f"Unexpected bus count: {inventory['bus_count']}")
    if inventory["line_label_count"] == 0:
        raise RuntimeError("No line-like labels were discovered")

    log("scenario inventory done")
    return {
        "power_flow_job_count": len(pf_job),
        "emt_job_count": len(emt_job),
        "config_count": len(config),
        "inventory": inventory,
    }


def scenario_target_resolution() -> dict[str, Any]:
    log("scenario target-resolution start")
    sa = build_case()
    revision = sa.getRevision()
    inventory = summarize_revision(revision)

    bus_label = inventory["sample_bus_labels"][0]
    gen_label = inventory["sample_generator_labels"][0]
    line_label = inventory["sample_line_labels"][0]

    resolved_bus = sa.convertLabelToKey([bus_label])["busKeys"]
    resolved_gen = sa.convertLabelToKey([gen_label])["busKeys"]
    resolved_line = sa.convertLabelToKey([line_label])["busKeys"]

    if not resolved_bus or not resolved_gen or not resolved_line:
        raise RuntimeError("Failed to resolve one or more sample labels")

    log("scenario target-resolution done")
    return {
        "bus_label": bus_label,
        "bus_keys": resolved_bus,
        "generator_label": gen_label,
        "generator_keys": resolved_gen,
        "line_label": line_label,
        "line_keys": resolved_line,
    }


def scenario_topology_precheck() -> dict[str, Any]:
    log("scenario topology-precheck start")
    sa = build_case()
    sa.refreshTopology()
    sa.generateNetwork(show=False)

    topo_components = len(sa.topo.get("components", {})) if sa.topo else 0
    graph_vertices = int(sa.g.vcount()) if sa.g is not None else 0
    graph_edges = int(sa.g.ecount()) if sa.g is not None else 0

    if topo_components == 0:
        raise RuntimeError("Topology refresh produced no components")
    if graph_vertices == 0:
        raise RuntimeError("Topology graph contains no vertices")

    log("scenario topology-precheck done")
    return {
        "topology_component_count": topo_components,
        "graph_vertex_count": graph_vertices,
        "graph_edge_count": graph_edges,
    }


def main() -> None:
    summary = {
        "inventory": scenario_inventory(),
        "target_resolution": scenario_target_resolution(),
        "topology_precheck": scenario_topology_precheck(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
