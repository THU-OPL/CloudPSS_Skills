from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from psa_skill_runtime import CONFIG_NAME, EMT_JOB_NAME, FLOW_JOB_NAME, MODEL_ID, configure_local_runtime, path_exists  # noqa: E402
from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402

DV_VALID_KEY = "有效通道索引"
EXPECTED_SELECTION_MODE = "auto_single_voltage_level"


def validate_result(result: dict) -> None:
    dv_result = result["dv_result"]
    si_result = result["si_result"]
    dudv_plot = result["dudv_plot"]
    bus_selection = result.get("bus_selection", {})
    plot_path = next(iter(dudv_plot.values()))

    if not dv_result[DV_VALID_KEY]:
        raise RuntimeError(f"No valid channels in DV result: {dv_result}")
    if "SI" not in si_result:
        raise RuntimeError(f"Missing SI result: {si_result}")
    if not path_exists(plot_path):
        raise RuntimeError(f"DUDV plot was not saved locally: {plot_path}")
    if not result.get("analysis_conclusion"):
        raise RuntimeError(f"Missing analysis conclusion: {result}")
    if bus_selection.get("mode") != EXPECTED_SELECTION_MODE:
        raise RuntimeError(f"Unexpected bus selection mode: {bus_selection}")
    if not bus_selection.get("selected_voltage_level_label"):
        raise RuntimeError(f"Missing selected voltage level label: {bus_selection}")
    if not bus_selection.get("selected_bus_keys"):
        raise RuntimeError(f"Missing selected bus keys: {bus_selection}")
    if result.get("screened_bus_count") != len(bus_selection.get("selected_bus_keys", [])):
        raise RuntimeError(f"Selected bus count mismatch: {bus_selection}, result={result}")
    for artifact_path in result.get("artifacts", {}).values():
        if not path_exists(artifact_path):
            raise RuntimeError(f"Saved artifact missing: {artifact_path}")


def main() -> None:
    export_dir = configure_local_runtime("disturbance-severity-analysis")

    sa = PowerSystemAnalysis()
    result = sa.run_disturbance_severity_analysis(
        cloudpss_model=MODEL_ID,
        flowJobName=FLOW_JOB_NAME,
        emtJobName=EMT_JOB_NAME,
        configName=CONFIG_NAME,
        analysis_mode="quick",
    )
    validate_result(result)

    print(
        json.dumps(
            {
                "ok": True,
                "export_dir": str(export_dir),
                **result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
