from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_transient_stability_report  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "transient-stability-report-generator"
    config = {
        "report": {
            "title": "IEEE3 Transient Stability Screening Report",
            "scenario": "model/CloudPSS/IEEE3 existing EMT scenario",
        },
        "assessment": {
            "base_frequency_hz": 50.0,
            "analysis_window": [0.0, 10.0],
            "prefault_window": [0.0, 0.5],
            "postfault_window": [9.0, 10.0],
            "settling_threshold_pu": 0.002,
            "max_speed_deviation_pu": 0.02,
            "voltage_low_limit_pu": 0.8,
            "voltage_recovery_limit_pu": 0.9,
            "rocof_window_samples": 5,
            "min_samples": 128,
        },
        "channels": {
            "speed_pu": ["#wr1:0", "#wr2:0", "#wr3:0"],
            "power": ["#P1:0", "#P2:0", "#P3:0"],
            "voltage": ["vac:0", "vac:1", "vac:2"],
            "auto_max_channels": 3,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "transient_stability_report",
            "generate_report": True,
        },
    }
    result = run_transient_stability_report(model, config=config, output_dir=output_dir)
    if result["summary"]["channel_count"] != 9:
        raise RuntimeError(f"Expected 9 channels, got {result['summary']['channel_count']}")
    if result["summary"]["assessed_channel_count"] < 3:
        raise RuntimeError(f"Expected at least 3 assessed channels, got {result['summary']['assessed_channel_count']}")
    support_kinds = {row["kind"] for row in result["channels"] if row["analysis"]["is_stable"] is None}
    if not {"voltage", "power"}.issubset(support_kinds):
        raise RuntimeError(f"Expected voltage and power supporting waveforms, got {sorted(support_kinds)}")
    for key in ["overall_assessment", "max_speed_deviation_pu", "max_rocof_hz_per_s", "min_voltage_pu"]:
        if key not in result["summary"]:
            raise RuntimeError(f"Missing summary field: {key}")
    for row in result["channels"]:
        analysis = row["analysis"]
        required = ["sample_count", "initial_value", "min_value", "max_value", "steady_value", "max_abs_deviation"]
        missing = [key for key in required if key not in analysis]
        if missing:
            raise RuntimeError(f"Missing fields for {row['channel']}: {missing}")
        if analysis["sample_count"] < config["assessment"]["min_samples"]:
            raise RuntimeError(f"Insufficient samples for {row['channel']}")
    for key in ["json_path", "csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
