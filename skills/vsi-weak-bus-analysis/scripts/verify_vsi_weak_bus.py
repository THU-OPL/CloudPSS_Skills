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

from psa_skill_runtime import CONFIG_NAME, EMT_JOB_NAME, FLOW_JOB_NAME, MODEL_ID, configure_local_runtime, first_existing_path, path_exists, select_bus_targets  # noqa: E402
from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402

BUS_LIMIT = 4


def main() -> None:
    export_dir = configure_local_runtime("vsi-weak-bus-analysis")

    sa = PowerSystemAnalysis()
    sa.initModelAndCreateSACanvas(MODEL_ID)
    bus_keys, bus_labels = select_bus_targets(sa, limit=BUS_LIMIT)

    power_flow = sa.power_flow_sample_simple_ramdom(
        FLOW_JOB_NAME,
        CONFIG_NAME,
        P_low=1.0,
        P_high=1.0,
    )
    if power_flow.get("status") != "success":
        raise RuntimeError(f"Power flow failed: {power_flow}")

    q_sources = sa.addVSIQSource(busKeys=bus_keys, dT=1.0)
    measure_info = sa.addVSIMeasure(
        EMT_JOB_NAME,
        q_sources["VSIQkeys"],
        NameKeys=bus_keys,
        dT=1.0,
        freq=100,
    )
    runner_id = sa.runProject(EMT_JOB_NAME, CONFIG_NAME, showLogs=False)
    vsi_result = sa.calculateVSI(
        EMT_JOB_NAME,
        measure_info["voltageMeasureK"],
        measure_info["dQMeasureK"],
        busLabels=bus_labels,
        dT=1.0,
    )

    vsi_path = first_existing_path(vsi_result, (".json",))
    waveform_path = first_existing_path(vsi_result, (".png",))
    vsi_map = vsi_result["VSIresultDict"]
    weak_bus = max(vsi_map.items(), key=lambda item: item[1])

    if len(vsi_map) != len(bus_labels):
        raise RuntimeError(f"Unexpected VSI result size: {vsi_result}")
    if not path_exists(vsi_path) or not path_exists(waveform_path):
        raise RuntimeError(f"VSI artifacts missing: {vsi_result}")

    print(
        json.dumps(
            {
                "ok": True,
                "export_dir": str(export_dir),
                "runner_id": runner_id,
                "bus_keys": bus_keys,
                "bus_labels": bus_labels,
                "measure_info": measure_info,
                "vsi_result": vsi_result,
                "weak_bus": {"label": weak_bus[0], "vsi": weak_bus[1]},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
