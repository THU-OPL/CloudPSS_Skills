from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_short_circuit_analysis  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "short-circuit-analysis"
    config = {
        "analysis": {
            "base_voltage_kv": 230.0,
            "power_scale_mw": 1.0,
            "voltage_scale_pu": 1.0,
            "analysis_window": [0.0, 10.0],
            "prefault_window": [0.0, 0.5],
            "fault_window": [2.0, 2.5],
            "postfault_window": [9.0, 10.0],
            "min_samples": 128,
        },
        "channels": {
            "equivalent_pairs": [
                {"power": "#P1:0", "voltage": "vac:0"},
                {"power": "#P2:0", "voltage": "vac:1"},
                {"power": "#P3:0", "voltage": "vac:2"},
            ],
            "auto_max_channels": 3,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "short_circuit_analysis",
            "generate_report": True,
        },
    }
    result = run_short_circuit_analysis(model, config=config, output_dir=output_dir)
    if result["summary"]["channel_count"] != 3:
        raise RuntimeError(f"Expected 3 channels, got {result['summary']['channel_count']}")
    if "estimated_from_power_voltage" not in result["summary"]["methods"]:
        raise RuntimeError(f"Expected estimated method, got {result['summary']['methods']}")
    for row in result["channels"]:
        analysis = row["analysis"]
        required = [
            "peak_current",
            "fault_rms_current",
            "prefault_rms_current",
            "postfault_rms_current",
            "short_circuit_mva",
        ]
        missing = [key for key in required if key not in analysis]
        if missing:
            raise RuntimeError(f"Missing fields for {row['channel']}: {missing}")
        if analysis["sample_count"] < config["analysis"]["min_samples"]:
            raise RuntimeError(f"Insufficient samples for {row['channel']}")
        if analysis["short_circuit_mva"] <= 0:
            raise RuntimeError(f"Non-positive short-circuit capacity for {row['channel']}")
    for key in ["json_path", "csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
