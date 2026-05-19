from __future__ import annotations

import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
for env_path in [ROOT / ".env", *[parent / ".env" for parent in ROOT.parents]]:
    if env_path.exists():
        load_dotenv(env_path)
        break

MODEL_ID = os.environ.get("CLOUDPSS_TEST_MODEL_RID", "model/yuanxuefeng/IEEE39")
FLOW_JOB_NAME = os.environ.get("CLOUDPSS_TEST_FLOW_JOB", "潮流计算方案 1")
EMT_JOB_NAME = os.environ.get("CLOUDPSS_TEST_EMT_JOB", "电磁暂态仿真方案 1")
CONFIG_NAME = os.environ.get("CLOUDPSS_TEST_CONFIG", "参数方案 1")
STATUS_KEY = "\u72b6\u6001"
TASKS_DIR = ROOT / "results" / "psa-batch-tasks" / "batch-contingency-screening"
LOCAL_SAVE_DIR = ROOT / "results" / "skill-local-export" / "batch-contingency-screening"
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


def configure_batch_environment() -> None:
    os.environ["PSA_TASKS_DIR"] = str(TASKS_DIR)
    os.environ["PSA_LOCAL_SAVE_DIR"] = str(LOCAL_SAVE_DIR)
    os.environ["RAY_NUM_CPUS"] = "1"
    os.environ["SAVETOLOCAL"] = "true"
    os.environ["SAVETOMINIO"] = "false"


def build_batch_flow() -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "name": "initModelAndCreateSACanvas",
            "params": {"cloudpss_model": MODEL_ID},
        },
        {
            "name": "power_flow_sample_simple_ramdom",
            "params": {
                "flowJobName": FLOW_JOB_NAME,
                "flowConfigname": CONFIG_NAME,
                "P_low": 1.0,
                "P_high": 1.0,
            },
        },
        {
            "name": "generate_random_fault_params_set_N_1",
            "params": {},
        },
    ]
    for spec in MEASURES:
        steps.append(
            {
                "name": "addComponentOutputMeasures",
                "params": {
                    "jobName": EMT_JOB_NAME,
                    "compRID": spec["compRID"],
                    "measuredKey": spec["measuredKey"],
                    "conditions": [],
                    "plotName": spec["plotName"],
                    "freq": 200,
                },
            }
        )
    steps.extend(
        [
            {
                "name": "runProject",
                "params": {
                    "jobName": EMT_JOB_NAME,
                    "configName": CONFIG_NAME,
                    "showLogs": False,
                },
            },
            {
                "name": "extract_and_check_data",
                "params": {"jobName": EMT_JOB_NAME},
            },
        ]
    )
    return {"steps": steps}


def poll_status(
    status_getter,
    task_id: str,
    *,
    timeout_seconds: int = 1200,
    interval_seconds: int = 10,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status: dict[str, Any] | None = None
    while time.time() < deadline:
        last_status = status_getter(task_id)
        if last_status.get(STATUS_KEY) in {"completed", "failed"}:
            return last_status
        time.sleep(interval_seconds)
    raise TimeoutError(f"Timed out waiting for batch task {task_id}: {last_status}")


def summarize_batch_result(result_payload: dict[str, Any]) -> dict[str, Any]:
    result_items = result_payload.get("result", [])
    simulations: list[dict[str, Any]] = []
    for index, item in enumerate(result_items):
        if "error" in item:
            simulations.append({"index": index, "error": item["error"]})
            continue

        final_result = item.get("final_result", {})
        files_results = item.get("files_results", {})
        export_info = files_results.get("save_flow_emt_hdf5", {})
        flow_url = export_info.get("flow_url")
        emt_url = export_info.get("emt_url")
        simulations.append(
            {
                "index": index,
                "runner_id": final_result.get("runner_id"),
                "fault_info": final_result.get("fault_info"),
                "check_result": final_result.get("check_result"),
                "flow_url": flow_url,
                "emt_url": emt_url,
                "flow_exists": bool(flow_url and Path(flow_url).exists()),
                "emt_exists": bool(emt_url and Path(emt_url).exists()),
            }
        )

    summary = deepcopy(result_payload)
    summary["simulations"] = simulations
    return summary
