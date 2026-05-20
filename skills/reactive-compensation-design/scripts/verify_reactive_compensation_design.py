from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
os.environ.setdefault("SSC_MAX_ITERATION_COUNT", "4")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from psa_skill_runtime import CONFIG_NAME, EMT_JOB_NAME, FLOW_JOB_NAME, MODEL_ID, configure_local_runtime, first_existing_path, path_exists, select_bus_targets  # noqa: E402
from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402

BUS_LIMIT = 4
INITIAL_Q = 20.0


def build_vsi_reference() -> tuple[list[str], list[str], str, dict]:
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
        raise RuntimeError(f"Power flow failed during VSI reference stage: {power_flow}")

    q_sources = sa.addVSIQSource(busKeys=bus_keys, dT=1.0)
    measure_info = sa.addVSIMeasure(
        EMT_JOB_NAME,
        q_sources["VSIQkeys"],
        NameKeys=bus_keys,
        dT=1.0,
        freq=100,
    )
    sa.runProject(EMT_JOB_NAME, CONFIG_NAME, showLogs=False)
    vsi_result = sa.calculateVSI(
        EMT_JOB_NAME,
        measure_info["voltageMeasureK"],
        measure_info["dQMeasureK"],
        busLabels=bus_labels,
        dT=1.0,
    )
    vsi_path = first_existing_path(vsi_result, (".json",))
    if not path_exists(vsi_path):
        raise RuntimeError(f"VSI result file missing: {vsi_result}")
    return bus_keys, bus_labels, vsi_path, vsi_result


def main() -> None:
    export_dir = configure_local_runtime("reactive-compensation-design")
    bus_keys, bus_labels, vsi_path, vsi_result = build_vsi_reference()

    sa = PowerSystemAnalysis()
    sa.initModelAndCreateSACanvas(MODEL_ID)

    power_flow = sa.power_flow_sample_simple_ramdom(
        FLOW_JOB_NAME,
        CONFIG_NAME,
        P_low=1.0,
        P_high=1.0,
    )
    if power_flow.get("status") != "success":
        raise RuntimeError(f"Power flow failed during compensation stage: {power_flow}")

    pf_runner_id = sa.runProject(FLOW_JOB_NAME, CONFIG_NAME, showLogs=False)
    sync_result = sa.batchAddSyncComp(
        busKeys=bus_keys,
        pfresultID=pf_runner_id,
        Q=[INITIAL_Q for _ in bus_keys],
    )
    fault_context = sa.generate_random_fault_params_set_N_1()
    screened_bus = sa.addVoltageMeasures(
        EMT_JOB_NAME,
        Keys=bus_keys,
        freq=200,
        PlotName="S06-Voltage",
    )
    compensation_result = sa.iterativeSolutionQ(
        EMT_JOB_NAME,
        CONFIG_NAME,
        vsi_path,
        sync_result["Syncids"],
        sync_result["Tranids"],
        sync_result["Q"],
    )

    task_ids = compensation_result.get("TaskIDs", [])
    if not task_ids:
        raise RuntimeError(f"No iterative simulation task ids returned: {compensation_result}")

    print(
        json.dumps(
            {
                "ok": True,
                "export_dir": str(export_dir),
                "bus_keys": bus_keys,
                "bus_labels": bus_labels,
                "vsi_path": vsi_path,
                "vsi_result": vsi_result,
                "fault_context": fault_context,
                "screened_bus_count": len(screened_bus),
                "sync_result": sync_result,
                "compensation_result": compensation_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

