from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

for env_path in [ROOT / ".env", *[parent / ".env" for parent in ROOT.parents]]:
    if env_path.exists():
        load_dotenv(env_path)
        break

from psa.tool_box.PowerSystemAnalysis import PowerSystemAnalysis  # noqa: E402


MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/CloudPSS/IEEE39")
FLOW_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
EMT_JOB_NAME = os.environ.get("CLOUDPSS_TEST_EMT_JOB", "电磁暂态仿真方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")
MEASURES = [
    {
        "compRID": "model/CloudPSS/_newBus_3p",
        "measuredKey": "Vrms",
        "plotName": "\u6bcd\u7ebf\u7535\u538b",
    },
    {
        "compRID": "model/CloudPSS/SyncGeneratorRouter",
        "measuredKey": "PT_o",
        "plotName": "\u53d1\u7535\u673a\u529f\u7387",
    },
    {
        "compRID": "model/CloudPSS/SyncGeneratorRouter",
        "measuredKey": "wr_o",
        "plotName": "\u53d1\u7535\u673a\u8f6c\u901f",
    },
    {
        "compRID": "model/CloudPSS/SyncGeneratorRouter",
        "measuredKey": "theta_o",
        "plotName": "\u53d1\u7535\u673a\u529f\u89d2",
    },
]


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def configure_case() -> PowerSystemAnalysis:
    sa = PowerSystemAnalysis()
    log(f"init-start model={MODEL_ID}")
    sa.initModelAndCreateSACanvas(MODEL_ID)
    sa.save_to_local = False
    sa.save_to_minio = False
    log("init-done")
    return sa


def run_single_random_n1() -> dict[str, Any]:
    sa = configure_case()

    power_flow = sa.power_flow_sample_simple_ramdom(
        FLOW_JOB_NAME,
        CONFIG_NAME,
        P_low=1.0,
        P_high=1.0,
    )
    if power_flow.get("status") != "success":
        raise RuntimeError(f"Power flow failed: {power_flow}")

    fault_context = sa.generate_random_fault_params_set_N_1()

    applied_measures: list[dict[str, Any]] = []
    for spec in MEASURES:
        sa.addComponentOutputMeasures(
            EMT_JOB_NAME,
            compRID=spec["compRID"],
            measuredKey=spec["measuredKey"],
            conditions=[],
            plotName=spec["plotName"],
            freq=200,
        )
        applied_measures.append(spec)

    runner_id = sa.runProject(EMT_JOB_NAME, CONFIG_NAME, showLogs=False)
    extract_result = sa.extract_and_check_data(
        EMT_JOB_NAME,
        transKey=fault_context.get("transKey"),
        fault_start_time=fault_context.get("fault_start_time"),
        cut_time=fault_context.get("cut_time"),
        fault_type_index=fault_context.get("fault_type_index"),
    )

    if "check_result" not in extract_result:
        raise RuntimeError(f"Missing check_result in extract output: {extract_result}")

    return {
        "ok": True,
        "model": MODEL_ID,
        "power_flow": power_flow,
        "fault_context": fault_context,
        "measures": applied_measures,
        "runner_id": runner_id,
        "extract_result": extract_result,
    }


def main() -> None:
    summary = run_single_random_n1()
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

