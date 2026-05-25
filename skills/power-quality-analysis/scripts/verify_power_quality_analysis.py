from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_power_quality_analysis  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "power-quality-analysis"
    config = {
        "analysis": {
            "fundamental_freq": 50.0,
            "max_harmonic": 25,
            "analysis_window": [8.0, 10.0],
            "event_window": [0.0, 10.0],
            "reference_window": [0.0, 0.5],
            "min_samples": 128,
            "limits": {
                "thd_percent": 5.0,
                "single_harmonic_percent": 3.0,
                "voltage_dip_percent": 10.0,
                "voltage_swell_percent": 10.0,
                "unbalance_percent": 2.0,
                "dc_offset_percent": 1.0,
                "flicker_proxy_percent": 3.0,
            },
        },
        "channels": {
            "voltage": ["vac:0", "vac:1", "vac:2"],
            "three_phase": [{"name": "vac", "a": "vac:0", "b": "vac:1", "c": "vac:2"}],
            "auto_max_channels": 3,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "power_quality_analysis",
            "generate_report": True,
            "export_harmonics": True,
        },
    }
    result = run_power_quality_analysis(model, config=config, output_dir=output_dir)
    if result["summary"]["channel_count"] != 3:
        raise RuntimeError(f"Expected 3 channels, got {result['summary']['channel_count']}")
    if result["summary"]["three_phase_group_count"] != 1:
        raise RuntimeError(f"Expected 1 three-phase group, got {result['summary']['three_phase_group_count']}")
    if not result.get("job_id"):
        raise RuntimeError("Missing CloudPSS job id")
    required_channel_fields = [
        "rms",
        "fundamental",
        "thd_percent",
        "max_single_harmonic_percent",
        "voltage_event",
        "dc_offset_percent",
    ]
    for row in result["channels"]:
        analysis = row["analysis"]
        missing = [key for key in required_channel_fields if key not in analysis]
        if missing:
            raise RuntimeError(f"Missing fields for {row['channel']}: {missing}")
        if analysis["sample_count"] < config["analysis"]["min_samples"]:
            raise RuntimeError(f"Insufficient samples for {row['channel']}")
        if analysis["fundamental"]["rms"] <= 0:
            raise RuntimeError(f"Invalid fundamental RMS for {row['channel']}")
    group = result["three_phase_groups"][0]["analysis"]
    for key in ["rms_unbalance_percent", "sequence_unbalance_percent", "rms_a", "rms_b", "rms_c"]:
        if key not in group:
            raise RuntimeError(f"Missing three-phase field: {key}")
    for key in ["json_path", "csv_path", "harmonics_csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
