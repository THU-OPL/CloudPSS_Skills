from __future__ import annotations

import json
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_fault_severity_scan  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "fault-severity-scan"
    config = {
        "fault_point": {
            "fault_bus": None,
            "fault_type": "three_phase",
            "fault_time": 2.5,
            "fault_duration": 0.2,
            "fault_resistance": 0.01,
        },
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
            "trace_name": "vac:0",
            "time_windows": {
                "prefault": [2.42, 2.44],
                "fault": [2.56, 2.58],
                "postfault": [2.92, 2.94],
            },
        },
        "output": {
            "path": str(output_dir),
            "prefix": "fault_severity_scan",
            "generate_report": True,
        },
    }
    result = run_fault_severity_scan(model, config=config, output_dir=output_dir)
    if not result["results"]:
        raise RuntimeError("No severity-scan results were produced")
    if "fault_trend" not in result or "gap_trend" not in result:
        raise RuntimeError("Trend fields missing from result")
    for key in ["json_path", "csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
