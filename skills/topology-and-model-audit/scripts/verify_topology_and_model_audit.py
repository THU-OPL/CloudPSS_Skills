from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT.parent
for source_path in [ROOT / "src"]:
    if source_path.exists() and str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

os.environ.setdefault("CET_MAX_RETRY_COUNT", "2")
os.environ.setdefault("CET_RETRY_SLEEP_SECONDS", "5")
os.environ.setdefault("CET_STATUS_CHECK_INTERVAL", "2")

repo_env = ROOT / ".env"
if repo_env.exists():
    load_dotenv(repo_env)
elif not os.getenv("SIMSTUDIO_TOKEN") or not os.getenv("CLOUDPSS_API_URL"):
    if os.getenv("CLOUDPSS_IGNORE_PARENT_ENV", "").lower() not in {"1", "true", "yes"}:
        for parent in ROOT.parents:
            env_path = parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                break

from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402


MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/CloudPSS/IEEE39")
FLOW_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")
MIN_BUS_COUNT = int(os.environ.get("CLOUDPSS_TEST_MIN_BUS_COUNT", "39"))
ENABLE_TOPOLOGY_API = os.environ.get("CLOUDPSS_ENABLE_TOPOLOGY_API", "").lower() in {"1", "true", "yes"}
BUS_RID = "model/CloudPSS/_newBus_3p"
LINE_RID = "model/CloudPSS/TransmissionLine"
TRANSFORMER_RIDS = {
    "model/CloudPSS/_newTransformer_3p2w",
    "model/CloudPSS/_newTransformer_3p3w",
}
GENERATOR_RIDS = {
    "model/CloudPSS/SyncGeneratorRouter",
    "model/CloudPSS/_newACVoltageSource_3p",
    "model/CloudPSS/WGSource",
    "model/CloudPSS/PVStation",
}
LOAD_RIDS = {"model/CloudPSS/_newExpLoad_3p"}


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def build_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    result = sa.initModelAndCreateSACanvas(cloudpss_model=MODEL_ID)
    log(f"init-done result={result}")
    return sa


def component_cells(revision: dict[str, Any]) -> list[dict[str, Any]]:
    cells = revision["implements"]["diagram"]["cells"]
    return [
        {"id": key, **value}
        for key, value in cells.items()
        if isinstance(value, dict) and "definition" in value and "shape" in value
    ]


def split_cells(revision: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = revision["implements"]["diagram"]["cells"]
    components: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for key, value in cells.items():
        if not isinstance(value, dict):
            continue
        item = {"id": key, **value}
        if value.get("shape") == "diagram-edge":
            edges.append(item)
        elif "definition" in value and "shape" in value:
            components.append(item)
    return components, edges


def inventory_from_revision(revision: dict[str, Any]) -> dict[str, Any]:
    cells = component_cells(revision)
    definitions = Counter(str(cell.get("definition")) for cell in cells)
    labels = [cell.get("label") for cell in cells if isinstance(cell.get("label"), str)]
    duplicate_labels = {
        label: count
        for label, count in Counter(label for label in labels if label).items()
        if count > 1
    }
    empty_label_ids = [
        cell["id"]
        for cell in cells
        if not isinstance(cell.get("label"), str) or not cell.get("label")
    ]
    return {
        "component_count": len(cells),
        "definition_counts": dict(sorted(definitions.items())),
        "bus_count": definitions.get(BUS_RID, 0),
        "line_count": definitions.get(LINE_RID, 0),
        "transformer_count": sum(definitions.get(rid, 0) for rid in TRANSFORMER_RIDS),
        "generator_count": sum(definitions.get(rid, 0) for rid in GENERATOR_RIDS),
        "load_count": sum(definitions.get(rid, 0) for rid in LOAD_RIDS),
        "empty_label_count": len(empty_label_ids),
        "sample_empty_label_ids": empty_label_ids[:10],
        "duplicate_label_count": len(duplicate_labels),
        "sample_duplicate_labels": dict(list(sorted(duplicate_labels.items()))[:10]),
    }


def normalize_cell_id(cell_id: Any) -> str | None:
    if not isinstance(cell_id, str) or not cell_id:
        return None
    return cell_id[1:] if cell_id.startswith("/") else cell_id


def endpoint_cell(edge: dict[str, Any], key: str) -> str | None:
    endpoint = edge.get(key)
    if not isinstance(endpoint, dict):
        return None
    return normalize_cell_id(endpoint.get("cell"))


def summarize_revision_topology(revision: dict[str, Any]) -> dict[str, Any]:
    components, edges = split_cells(revision)
    component_by_id = {cell["id"]: cell for cell in components}
    adjacency: dict[str, set[str]] = {cell["id"]: set() for cell in components}
    graph_edges: list[dict[str, str]] = []
    dangling_edges: list[dict[str, Any]] = []

    for edge in edges:
        source = endpoint_cell(edge, "source")
        target = endpoint_cell(edge, "target")
        if source in component_by_id and target in component_by_id:
            adjacency[source].add(target)
            adjacency[target].add(source)
            graph_edges.append({"edge_id": edge["id"], "source": source, "target": target})
        else:
            dangling_edges.append({"edge_id": edge["id"], "source": source, "target": target})

    pin_to_components: dict[str, list[str]] = defaultdict(list)
    empty_pins: list[dict[str, str]] = []
    for cell in components:
        for port, pin in (cell.get("pins") or {}).items():
            pin_text = str(pin)
            if not pin_text:
                empty_pins.append({"component": cell["id"], "port": str(port)})
                continue
            pin_to_components[pin_text].append(cell["id"])

    single_terminal_pins = {
        pin: ids for pin, ids in pin_to_components.items() if len(ids) == 1
    }
    isolated_vertices = [
        {
            "component": component_id,
            "label": component_by_id[component_id].get("label"),
            "definition": component_by_id[component_id].get("definition"),
        }
        for component_id, neighbors in adjacency.items()
        if not neighbors
    ]
    return {
        "topology_source": "revision_diagram_edges",
        "topology_component_count": len(components),
        "diagram_edge_count": len(edges),
        "graph_edge_count": len(graph_edges),
        "pin_network_count": len(pin_to_components),
        "graph_vertex_count": len(components),
        "dangling_edge_count": len(dangling_edges),
        "sample_dangling_edges": dangling_edges[:10],
        "empty_pin_count": len(empty_pins),
        "sample_empty_pins": empty_pins[:10],
        "single_terminal_pin_count": len(single_terminal_pins),
        "sample_single_terminal_pins": {
            pin: ids for pin, ids in list(sorted(single_terminal_pins.items()))[:10]
        },
        "isolated_vertex_count": len(isolated_vertices),
        "sample_isolated_vertices": isolated_vertices[:10],
    }


def optional_cloudpss_topology_api(sa: PowerSystemAnalysis) -> dict[str, Any]:
    if not ENABLE_TOPOLOGY_API:
        return {"enabled": False}
    try:
        sa.refreshTopology()
        sa.generateNetwork(show=False)
        return {
            "enabled": True,
            "available": True,
            "topology_component_count": len(sa.topo.get("components", {})) if sa.topo else 0,
            "graph_vertex_count": int(sa.g.vcount()) if sa.g is not None else 0,
            "graph_edge_count": int(sa.g.ecount()) if sa.g is not None else 0,
        }
    except Exception as exc:
        return {"enabled": True, "available": False, "error": str(exc)}


def run_power_flow_validation(sa: PowerSystemAnalysis) -> dict[str, Any]:
    log("power-flow validation start")
    runner_id = sa.runProject(jobName=FLOW_JOB_NAME, configName=CONFIG_NAME, showLogs=False)
    bus_rows = sa.get_bus_all_pf_result()
    voltages = [float(row[2]) for row in bus_rows]
    log("power-flow validation done")
    return {
        "runner_id": runner_id,
        "bus_count": len(bus_rows),
        "v_min_pu": min(voltages),
        "v_max_pu": max(voltages),
        "v_avg_pu": sum(voltages) / len(voltages),
    }


def main() -> None:
    sa = build_case()
    revision = sa.getRevision()
    inventory = inventory_from_revision(revision)

    log("revision-topology audit start")
    topology = summarize_revision_topology(revision)
    cloudpss_topology_api = optional_cloudpss_topology_api(sa)
    power_flow_validation = run_power_flow_validation(sa)
    log("revision-topology audit done")

    passed = (
        inventory["bus_count"] >= MIN_BUS_COUNT
        and inventory["line_count"] > 0
        and topology["topology_component_count"] > 0
        and topology["graph_vertex_count"] > 0
        and topology["graph_edge_count"] > 0
        and power_flow_validation["bus_count"] >= MIN_BUS_COUNT
    )
    if not passed:
        raise RuntimeError(
            "Topology audit failed minimum checks: "
            + json.dumps(
                {"inventory": inventory, "topology": topology},
                ensure_ascii=False,
            )
        )

    summary = {
        "ok": True,
        "model": MODEL_ID,
        "revision_inventory": inventory,
        "topology_summary": topology,
        "cloudpss_topology_api": cloudpss_topology_api,
        "power_flow_validation": power_flow_validation,
        "model_quality": {
            "empty_label_count": inventory["empty_label_count"],
            "duplicate_label_count": inventory["duplicate_label_count"],
            "isolated_vertex_count": topology["isolated_vertex_count"],
            "dangling_edge_count": topology["dangling_edge_count"],
            "empty_pin_count": topology["empty_pin_count"],
            "single_terminal_pin_count": topology["single_terminal_pin_count"],
        },
        "pass": passed,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

