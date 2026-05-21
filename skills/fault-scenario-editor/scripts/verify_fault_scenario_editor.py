from __future__ import annotations

import json
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import (  # noqa: E402
    DEFAULT_MODEL_RID,
    build_fault_scenario_blueprint,
    configure_token,
    export_blueprint,
    load_model_from_source,
    render_blueprint_markdown,
)


def main() -> None:
    configure_token()
    model = load_model_from_source(DEFAULT_MODEL_RID)
    blueprint = build_fault_scenario_blueprint(model)

    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "fault-scenario-editor"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "fault-scenario-editor-blueprint.json"
    md_path = output_dir / "fault-scenario-editor-blueprint.md"

    export_blueprint(blueprint, json_path)
    md_path.write_text(render_blueprint_markdown(blueprint), encoding="utf-8")

    summary = {
        "ok": True,
        "skill": "fault-scenario-editor",
        "model_rid": blueprint["model"]["rid"],
        "revision_hash": blueprint["model"].get("revision_hash"),
        "fault_component_id": blueprint["anchors"]["fault"].get("id"),
        "fault_component_label": blueprint["anchors"]["fault"].get("label"),
        "measurement_channel": blueprint["anchors"]["measurement"].get("name"),
        "fault_component_count": blueprint["model"]["fault_component_count"],
        "channel_count": blueprint["model"]["channel_count"],
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "downstream_skills": list(blueprint["downstream_contract"].keys()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
