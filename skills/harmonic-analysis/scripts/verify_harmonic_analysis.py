from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_harmonic_analysis  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "harmonic-analysis"
    config = {
        "analysis": {
            "fundamental_freq": 50.0,
            "max_harmonic": 25,
            "thd_limit_percent": 5.0,
            "analysis_window": None,
            "min_samples": 128,
        },
        "channels": {
            "voltage": ["vac:0", "vac:1", "vac:2"],
            "auto_max_channels": 3,
        },
        "output": {
            "path": str(output_dir),
            "prefix": "harmonic_analysis",
            "generate_report": True,
            "export_spectrum": True,
        },
    }
    result = run_harmonic_analysis(model, config=config, output_dir=output_dir)
    if result["summary"]["channel_count"] <= 0:
        raise RuntimeError("No channels analyzed")
    for row in result["channels"]:
        analysis = row["analysis"]
        if "thd_percent" not in analysis or "fundamental" not in analysis or "harmonics" not in analysis:
            raise RuntimeError(f"Incomplete harmonic result for {row['channel']}")
        if analysis["sample_count"] < config["analysis"]["min_samples"]:
            raise RuntimeError(f"Insufficient samples for {row['channel']}")
    for key in ["json_path", "csv_path", "spectrum_csv_path", "markdown_path"]:
        path = Path(result["artifacts"][key])
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {path}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
