from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cloudpss import Model, setToken


DEFAULT_MODEL_RID = os.environ.get("CLOUDPSS_TEST_EMT_MODEL_RID", "model/<your-account>/IEEE3")
FAULT_DEFINITION = "model/CloudPSS/_newFaultResistor_3p"
CHANNEL_DEFINITION = "model/CloudPSS/_newChannel"
BUS_DEFINITION = "model/CloudPSS/_newBus_3p"
GENERATOR_DEFINITION = "model/CloudPSS/SyncGeneratorRouter"
LINE_LABEL_HINT = "TLine_3p-"


def load_token(token_path: str = ".cloudpss_token") -> str:
    env_values = _find_env_values()
    env_token = os.environ.get("SIMSTUDIO_TOKEN") or env_values.get("SIMSTUDIO_TOKEN")
    if env_token:
        api_url = os.environ.get("CLOUDPSS_API_URL") or env_values.get("CLOUDPSS_API_URL")
        if api_url and not os.environ.get("CLOUDPSS_API_URL"):
            os.environ["CLOUDPSS_API_URL"] = api_url
        return env_token.strip()

    path = Path(token_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing token file: {path}")
    return path.read_text(encoding="utf-8").strip()


def configure_token(token_path: str = ".cloudpss_token") -> str:
    token = load_token(token_path)
    setToken(token)
    return token


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


def assert_allowed_model_source(source: str) -> None:
    if "<your-account>" in source:
        raise ValueError(
            "Set CLOUDPSS_TEST_EMT_MODEL_RID or pass an EMT-ready model RID under your own account. "
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


def _component_record(component_id: str, component: Any) -> dict[str, Any]:
    args = getattr(component, "args", {}) or {}
    label = getattr(component, "label", None) or args.get("label") or args.get("Name")
    name = getattr(component, "name", None) or args.get("Name")
    return {
        "id": component_id,
        "label": label,
        "name": name,
        "definition": getattr(component, "definition", None),
        "args": args,
    }


def list_components(model) -> list[dict[str, Any]]:
    return [_component_record(component_id, component) for component_id, component in model.getAllComponents().items()]


def _unique_labels(cells: list[dict[str, Any]], *, definition: str | None = None, label_contains: str | None = None) -> list[str]:
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


def summarize_model(model) -> dict[str, Any]:
    cells = list_components(model)
    fault_components = [cell for cell in cells if cell.get("definition") == FAULT_DEFINITION]
    channel_components = [cell for cell in cells if cell.get("definition") == CHANNEL_DEFINITION]
    bus_labels = _unique_labels(cells, definition=BUS_DEFINITION)
    generator_labels = _unique_labels(cells, definition=GENERATOR_DEFINITION)
    line_labels = _unique_labels(cells, label_contains=LINE_LABEL_HINT)

    revision = getattr(model, "revision", None)
    revision_hash = None
    if revision is not None:
        revision_hash = getattr(revision, "hash", None)
        if not revision_hash and hasattr(revision, "toJSON"):
            revision_hash = revision.toJSON().get("hash")

    return {
        "name": getattr(model, "name", ""),
        "rid": getattr(model, "rid", ""),
        "revision_hash": revision_hash,
        "component_count": len(cells),
        "fault_component_count": len(fault_components),
        "channel_count": len(channel_components),
        "bus_count": len(bus_labels),
        "generator_count": len(generator_labels),
        "line_label_count": len(line_labels),
        "sample_bus_labels": bus_labels[:5],
        "sample_generator_labels": generator_labels[:5],
        "sample_line_labels": line_labels[:5],
        "sample_fault_components": fault_components[:5],
        "sample_channel_components": channel_components[:5],
    }


def _pick_component(
    candidates: list[dict[str, Any]],
    *,
    preferred_label: str | None = None,
    preferred_name: str | None = None,
) -> dict[str, Any]:
    if preferred_label:
        for candidate in candidates:
            if preferred_label in {
                candidate.get("id"),
                candidate.get("label"),
                candidate.get("name"),
            }:
                return candidate
        for candidate in candidates:
            label = candidate.get("label")
            name = candidate.get("name")
            if (isinstance(label, str) and preferred_label in label) or (
                isinstance(name, str) and preferred_label in name
            ):
                return candidate

    if preferred_name:
        for candidate in candidates:
            name = candidate.get("name")
            label = candidate.get("label")
            if name == preferred_name or label == preferred_name:
                return candidate
        for candidate in candidates:
            name = candidate.get("name")
            label = candidate.get("label")
            if (isinstance(name, str) and preferred_name in name) or (
                isinstance(label, str) and preferred_name in label
            ):
                return candidate

    if candidates:
        return candidates[0]
    raise ValueError("No matching component was found")


def select_fault_anchor(model, preferred_label: str | None = None) -> dict[str, Any]:
    candidates = [cell for cell in list_components(model) if cell.get("definition") == FAULT_DEFINITION]
    if not candidates:
        raise ValueError("未找到故障元件")
    return _pick_component(candidates, preferred_label=preferred_label)


def select_measurement_anchor(model, preferred_name: str = "vac") -> dict[str, Any]:
    candidates = [cell for cell in list_components(model) if cell.get("definition") == CHANNEL_DEFINITION]
    if not candidates:
        raise ValueError("未找到量测通道")
    return _pick_component(candidates, preferred_name=preferred_name)


def build_scenario_templates(
    fault_anchor: dict[str, Any],
    measurement_anchor: dict[str, Any],
    *,
    bus_labels: list[str],
) -> dict[str, Any]:
    trace_name = measurement_anchor.get("name") or measurement_anchor.get("label") or "vac:0"
    fault_bus = bus_labels[0] if bus_labels else None
    fault_point = {
        "fault_bus": fault_bus,
        "fault_type": "three_phase",
        "fault_time": 2.5,
        "fault_duration": 0.2,
        "fault_resistance": 0.01,
    }

    return {
        "emt_fault_study": {
            "fault_point": fault_point,
            "breaker_action": {
                "mode": "trip_and_reclose",
                "trip_time": 2.7,
                "reclose_time": 2.9,
            },
            "baseline": {
                "enabled": True,
                "fs": 2.5,
                "fe": 2.7,
                "chg": 0.01,
                "description": "基线故障",
            },
            "delayed_clearing": {
                "enabled": True,
                "fs": 2.5,
                "fe": 2.9,
                "chg": 0.01,
                "description": "延长故障切除时间",
            },
            "mild_fault": {
                "enabled": True,
                "fs": 2.5,
                "fe": 2.7,
                "chg": 10000.0,
                "description": "较轻故障",
            },
        },
        "fault_clearing_scan": {
            "fault_point": fault_point,
            "breaker_action": {
                "mode": "trip_after_scan",
                "clearing_policy": "vary_fe",
            },
            "scan": {
                "fs": 2.5,
                "fe_values": [2.70, 2.75, 2.80, 2.85, 2.90],
                "chg": 0.01,
            },
            "assessment": {
                "trace_name": trace_name,
                "study_time": 2.95,
            },
        },
        "fault_severity_scan": {
            "fault_point": fault_point,
            "breaker_action": {
                "mode": "keep_clear_time_fixed",
                "clear_time": 2.7,
            },
            "scan": {
                "fs": 2.5,
                "fe": 2.7,
                "chg_values": [0.01, 0.1, 1.0, 10.0, 100.0],
            },
            "assessment": {
                "trace_name": trace_name,
                "time_windows": {
                    "prefault": [2.42, 2.44],
                    "fault": [2.56, 2.58],
                    "postfault": [2.92, 2.94],
                },
            },
        },
        "editable_fields": ["fs", "fe", "chg", "trace_name"],
        "selected_fault_component_id": fault_anchor.get("id"),
        "selected_measurement_channel": trace_name,
        "fault_bus": fault_bus,
    }


def build_fault_scenario_blueprint(
    model,
    *,
    preferred_fault_label: str | None = None,
    preferred_channel_name: str = "vac",
) -> dict[str, Any]:
    summary = summarize_model(model)
    fault_anchor = select_fault_anchor(model, preferred_label=preferred_fault_label)
    measurement_anchor = select_measurement_anchor(model, preferred_name=preferred_channel_name)

    return {
        "skill": "fault-scenario-editor",
        "model": summary,
        "anchors": {
            "fault": fault_anchor,
            "measurement": measurement_anchor,
        },
        "inventory": {
            "fault_components": summary["sample_fault_components"],
            "channels": summary["sample_channel_components"],
            "bus_labels": summary["sample_bus_labels"],
            "generator_labels": summary["sample_generator_labels"],
            "line_labels": summary["sample_line_labels"],
        },
        "scenario_templates": build_scenario_templates(
            fault_anchor,
            measurement_anchor,
            bus_labels=summary["sample_bus_labels"],
        ),
        "fault_scene_fields": {
            "fault_point": [
                "fault_bus",
                "fault_type",
                "fault_time",
                "fault_duration",
                "fault_resistance",
            ],
            "breaker_action": [
                "mode",
                "trip_time",
                "reclose_time",
                "clearing_policy",
                "clear_time",
            ],
            "scenario_dimensions": [
                "fs",
                "fe",
                "chg",
                "fe_values",
                "chg_values",
                "trace_name",
            ],
        },
        "downstream_contract": {
            "emt_fault_study": [
                "baseline",
                "delayed_clearing",
                "mild_fault",
            ],
            "fault_clearing_scan": [
                "scan.fs",
                "scan.fe_values",
                "assessment.trace_name",
            ],
            "fault_severity_scan": [
                "scan.fs",
                "scan.fe",
                "scan.chg_values",
                "assessment.trace_name",
            ],
        },
        "limitations": [
            "This skill does not run EMT jobs.",
            "This skill does not edit and save a new cloud model revision.",
            "If the model has no fault resistor or no measurement channel, the build fails.",
        ],
    }


def export_blueprint(blueprint: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")


def render_blueprint_markdown(blueprint: dict[str, Any]) -> str:
    model = blueprint["model"]
    fault = blueprint["anchors"]["fault"]
    measurement = blueprint["anchors"]["measurement"]
    templates = blueprint["scenario_templates"]

    lines = [
        "# Fault Scenario Editor Blueprint",
        "",
        f"- Model: `{model['name']}`",
        f"- RID: `{model['rid']}`",
        f"- Revision: `{model.get('revision_hash')}`",
        f"- Fault anchor: `{fault.get('label') or fault.get('id')}`",
        f"- Measurement anchor: `{measurement.get('name') or measurement.get('label')}`",
        "",
        "## Inventory",
        "",
        f"- Fault components: {model['fault_component_count']}",
        f"- Channels: {model['channel_count']}",
        f"- Buses: {model['bus_count']}",
        f"- Generators: {model['generator_count']}",
        f"- Line labels: {model['line_label_count']}",
        "",
        "## Scene Fields",
        "",
    ]

    for group_name, fields in blueprint["fault_scene_fields"].items():
        lines.append(f"- {group_name}: {', '.join(fields)}")

    lines.extend(
        [
            "",
            "## Downstream Templates",
            "",
        ]
    )

    for skill_name, template in templates.items():
        if skill_name == "editable_fields":
            continue
        if skill_name in {"selected_fault_component_id", "selected_measurement_channel"}:
            continue
        lines.append(f"### {skill_name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(template, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## Limits",
            "",
        ]
    )
    for item in blueprint["limitations"]:
        lines.append(f"- {item}")

    return "\n".join(lines)
