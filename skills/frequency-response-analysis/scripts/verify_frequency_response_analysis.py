from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_frequency_response_analysis  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "frequency-response-analysis"
    config = {
        "analysis": {
            "base_frequency_hz": 50.0,
            "analysis_window": [0.0, 10.0],
            "initial_window": [0.0, 0.5],
            "steady_window": [9.0, 10.0],
            "settling_threshold_hz": 0.05,
            "rocof_window_samples": 5,
            "min_samples": 128,
        },
        "channels": {
            "speed_pu": ["#wr1:0", "#wr2:0", "#wr3:0"],
            "auto_max_channels": 3,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "frequency_response_analysis",
            "generate_report": True,
        },
    }
    result = run_frequency_response_analysis(model, config=config, output_dir=output_dir)
    if result["summary"]["channel_count"] != 3:
        raise RuntimeError(f"Expected 3 channels, got {result['summary']['channel_count']}")
    for row in result["channels"]:
        analysis = row["analysis"]
        required = [
            "initial_frequency_hz",
            "min_frequency_hz",
            "max_frequency_hz",
            "steady_frequency_hz",
            "max_abs_deviation_hz",
            "max_rocof_hz_per_s",
        ]
        missing = [key for key in required if key not in analysis]
        if missing:
            raise RuntimeError(f"Missing fields for {row['channel']}: {missing}")
        if analysis["sample_count"] < config["analysis"]["min_samples"]:
            raise RuntimeError(f"Insufficient samples for {row['channel']}")
    for key in ["json_path", "csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
