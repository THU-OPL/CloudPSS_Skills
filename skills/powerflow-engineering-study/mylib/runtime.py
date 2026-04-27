from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import time

from cloudpss import Model, setToken


DEFAULT_READONLY_MODEL_RID = "model/holdme/IEEE39"
BUS_COLUMN = "Bus"
NODE_COLUMN = "Node"
VM_COLUMN = "<i>V</i><sub>m</sub> / pu"
VA_COLUMN = "<i>V</i><sub>a</sub> / deg"
P_GEN_COLUMN = "<i>P</i><sub>gen</sub> / MW"
Q_GEN_COLUMN = "<i>Q</i><sub>gen</sub> / MVar"
BRANCH_COLUMN = "Branch"
P_IJ_COLUMN = "<i>P</i><sub>ij</sub> / MW"
P_JI_COLUMN = "<i>P</i><sub>ji</sub> / MW"


def load_token(token_path: str = ".cloudpss_token") -> str:
    path = Path(token_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing token file: {path}")
    return path.read_text(encoding="utf-8").strip()


def configure_token(token_path: str = ".cloudpss_token") -> str:
    token = load_token(token_path)
    setToken(token)
    return token


def load_model_from_source(source: str):
    candidate = Path(source).expanduser()
    if candidate.exists():
        return Model.load(str(candidate))
    return Model.fetch(source)


def wait_for_completion(job, timeout: int = 300, interval: int = 2) -> None:
    start = time.time()
    while True:
        status = job.status()
        if status == 1:
            return
        if status == 2:
            raise RuntimeError("Power-flow job failed")
        if time.time() - start > timeout:
            raise TimeoutError("Power-flow job timed out")
        time.sleep(interval)


def table_rows(table: dict) -> list[dict]:
    columns = table["data"]["columns"]
    labels = [column.get("name") or column.get("title") or f"col_{index}" for index, column in enumerate(columns)]
    row_count = len(columns[0].get("data", [])) if columns else 0
    rows = []
    for row_index in range(row_count):
        row = {}
        for label, column in zip(labels, columns):
            row[label] = column.get("data", [None] * row_count)[row_index]
        rows.append(row)
    return rows


def run_powerflow_tables(model):
    job = model.runPowerFlow()
    wait_for_completion(job)
    result = job.result
    return table_rows(result.getBuses()[0]), table_rows(result.getBranches()[0])


def find_bus_row(rows: list[dict], *, bus_id: str | None = None, node_id: str | None = None) -> dict:
    for row in rows:
        if bus_id is not None and row.get(BUS_COLUMN) == bus_id:
            return row
        if node_id is not None and row.get(NODE_COLUMN) == node_id:
            return row
    raise KeyError(f"Bus not found: bus_id={bus_id}, node_id={node_id}")


def find_branch_row(rows: list[dict], branch_id: str) -> dict:
    for row in rows:
        if row.get(BRANCH_COLUMN) == branch_id:
            return row
    raise KeyError(f"Branch not found: {branch_id}")


def run_line_outage_study(model) -> dict:
    base_buses, base_branches = run_powerflow_tables(model)
    outage_model = Model(deepcopy(model.toJSON()))
    target_line = outage_model.getComponentByKey("canvas_0_126")
    outage_model.removeComponent(target_line.id)
    outage_buses, outage_branches = run_powerflow_tables(outage_model)
    target_branch = find_branch_row(base_branches, "canvas_0_126")
    return {
        "target_branch": {
            "id": "canvas_0_126",
            "from_bus": target_branch["From bus"],
            "to_bus": target_branch["To bus"],
            "base_p_ij": target_branch[P_IJ_COLUMN],
            "base_p_ji": target_branch[P_JI_COLUMN]
        },
        "from_bus_shift": {
            "base_vm": find_bus_row(base_buses, bus_id=target_branch["From bus"])[VM_COLUMN],
            "outage_vm": find_bus_row(outage_buses, bus_id=target_branch["From bus"])[VM_COLUMN]
        },
        "to_bus_shift": {
            "base_vm": find_bus_row(base_buses, bus_id=target_branch["To bus"])[VM_COLUMN],
            "outage_vm": find_bus_row(outage_buses, bus_id=target_branch["To bus"])[VM_COLUMN]
        },
        "outage_branch_count": len(outage_branches)
    }


def run_voltage_control_study(model) -> dict:
    base_buses, _ = run_powerflow_tables(model)
    adjusted_model = Model(deepcopy(model.toJSON()))
    gen30 = adjusted_model.getComponentByKey("canvas_2_303")
    adjusted_model.updateComponent(
        gen30.id,
        args={**gen30.args, "pf_V": {"source": "1.070", "傻exp": ""}},
    )
    adjusted_buses, _ = run_powerflow_tables(adjusted_model)
    base_row = find_bus_row(base_buses, node_id="canvas_2_303")
    adjusted_row = find_bus_row(adjusted_buses, node_id="canvas_2_303")
    return {
        "generator": "Gen30",
        "target_bus": {
            "bus_id": base_row[BUS_COLUMN],
            "base_vm": base_row[VM_COLUMN],
            "adjusted_vm": adjusted_row[VM_COLUMN],
            "base_q_gen": base_row[Q_GEN_COLUMN],
            "adjusted_q_gen": adjusted_row[Q_GEN_COLUMN]
        }
    }
