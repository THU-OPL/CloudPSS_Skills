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

from batch_workflow_common import (  # noqa: E402
    STATUS_KEY,
    build_batch_flow,
    configure_batch_environment,
    poll_status,
    summarize_batch_result,
)
from psa.tool_box.SimulationOrchestrator import (  # noqa: E402
    clear_batch_simulation_tasks,
    get_batch_simulation_result,
    get_step_temp,
    list_batch_simulation_tasks,
    query_batch_simulation_status,
    submit_batch_simulation,
)


def main() -> None:
    configure_batch_environment()

    template = get_step_temp()
    clear_info = clear_batch_simulation_tasks()
    submitted = submit_batch_simulation(
        flow=build_batch_flow(),
        num_simulations=1,
        num_cpus=1,
    )
    task_id = submitted["task_id"]
    status = poll_status(query_batch_simulation_status, task_id)
    tasks = list_batch_simulation_tasks(limit=10)
    result_payload = get_batch_simulation_result(task_id)
    summary = summarize_batch_result(result_payload)

    if status.get(STATUS_KEY) != "completed":
        raise RuntimeError(f"Batch task did not complete successfully: {status}")
    if summary.get("returned_count") != 1 or summary.get("total_count") != 1:
        raise RuntimeError(f"Unexpected batch result counts: {summary}")
    if any("error" in item for item in summary["simulations"]):
        raise RuntimeError(f"Per-simulation error detected: {summary['simulations']}")
    if not all(item.get("check_result") for item in summary["simulations"]):
        raise RuntimeError(f"Missing per-simulation check_result: {summary['simulations']}")

    print(
        json.dumps(
            {
                "ok": True,
                "template_step_names": [step["name"] for step in template["steps"]],
                "clear_info": clear_info,
                "submitted": submitted,
                "status": status,
                "tasks": tasks,
                "result": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
