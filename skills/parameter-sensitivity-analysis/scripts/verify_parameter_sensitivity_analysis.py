from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_parameter_sensitivity_analysis  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "parameter-sensitivity-analysis"
    config = {
        "scan": {
            "target": {"component": "newExpLoad-2", "arg": "p"},
            "values": [90.0, 100.0, 110.0],
            "reference": 100.0,
            "simulation_type": "emt",
            "timeout": 300,
        },
        "metrics": {
            "channels": ["#P1:0", "#P2:0", "#P3:0", "#wr1:0", "#wr2:0", "#wr3:0"],
            "metric_names": ["mean", "rms", "final"],
            "time_window": [0.0, 10.0],
            "min_samples": 128,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "parameter_sensitivity_analysis",
            "generate_report": True,
        },
    }
    result = run_parameter_sensitivity_analysis(model, config=config, output_dir=output_dir)
    if result["summary"]["successful_points"] != 3:
        raise RuntimeError(f"Expected 3 successful points, got {result['summary']['successful_points']}")
    if result["summary"]["metric_count"] < 6:
        raise RuntimeError(f"Expected at least 6 metrics, got {result['summary']['metric_count']}")
    if not result["sensitivity_ranking"]:
        raise RuntimeError("Missing sensitivity ranking")
    if all(abs(item["sensitivity"]) <= 1e-12 for item in result["sensitivity_ranking"]):
        raise RuntimeError("All sensitivities are zero")
    for row in result["scan_results"]:
        if not row.get("job_id"):
            raise RuntimeError(f"Missing job id for scan point: {row}")
        if not row.get("metrics"):
            raise RuntimeError(f"Missing metrics for scan point: {row}")
    for key in ["json_path", "csv_path", "scan_csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
