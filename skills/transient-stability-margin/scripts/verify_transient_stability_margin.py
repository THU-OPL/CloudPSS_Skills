from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_transient_stability_margin  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "transient-stability-margin"
    config = {
        "scenario": {
            "fault_start": 2.5,
            "fault_resistance": 0.01,
            "description": "IEEE3 existing three-phase fault component clearing-time margin screening",
        },
        "search": {
            "coarse_clearing_times": [0.15, 0.25, 0.4],
            "baseline_clearing_time": 0.15,
            "bisection_tolerance": 0.02,
            "max_bisection_iterations": 4,
            "timeout": 300,
        },
        "assessment": {
            "base_frequency_hz": 50.0,
            "analysis_window": [0.0, 10.0],
            "prefault_window": [0.0, 0.5],
            "postfault_window": [9.0, 10.0],
            "speed_channels": ["#wr1:0", "#wr2:0", "#wr3:0"],
            "support_channels": ["vac:0", "vac:1", "vac:2"],
            "max_speed_deviation_pu": 0.02,
            "final_speed_deviation_pu": 0.006,
            "settling_threshold_pu": 0.003,
            "max_rocof_hz_per_s": 10.0,
            "rocof_window_samples": 5,
            "min_samples": 128,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "transient_stability_margin",
            "generate_report": True,
        },
    }
    result = run_transient_stability_margin(model, config=config, output_dir=output_dir)
    if result["summary"]["total_emt_runs"] < 3:
        raise RuntimeError(f"Expected at least 3 EMT runs, got {result['summary']['total_emt_runs']}")
    if result["summary"]["cct_relation"] not in {"=", ">=", "<="}:
        raise RuntimeError(f"Invalid CCT relation: {result['summary']['cct_relation']}")
    if result["summary"]["stable_points"] < 1:
        raise RuntimeError("Expected at least one stable point for IEEE3 verification")
    for point in result["search_points"]:
        if not point.get("job_id"):
            raise RuntimeError(f"Missing job id: {point}")
        if point["assessed_channel_count"] < 3:
            raise RuntimeError(f"Expected at least 3 assessed channels: {point}")
        for key in ["max_speed_deviation_pu", "max_rocof_hz_per_s", "worst_channel"]:
            if key not in point:
                raise RuntimeError(f"Missing point field {key}: {point}")
    for key in ["cct_seconds", "cct_relation", "margin_seconds", "margin_percent", "search_status"]:
        if key not in result["summary"]:
            raise RuntimeError(f"Missing summary field: {key}")
    for key in ["json_path", "csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
