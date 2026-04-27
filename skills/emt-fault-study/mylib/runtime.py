from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import time

from cloudpss import Model, setToken


DEFAULT_MODEL_SOURCE = "model/holdme/IEEE3"
FAULT_DEFINITION = "model/CloudPSS/_newFaultResistor_3p"
CHANNEL_DEFINITION = "model/CloudPSS/_newChannel"
EMT_JOB_RID = "function/CloudPSS/emtps"
VOLTAGE_CHANNEL_NAME = "vac"
VOLTAGE_TRACE_NAME = "vac:0"
PREFAULT_WINDOW = (2.42, 2.44)
FAULT_WINDOW = (2.56, 2.58)
POSTFAULT_WINDOW = (2.92, 2.94)
LATE_RECOVERY_WINDOW = (2.96, 2.98)


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


def wait_for_completion(job, timeout: int = 300, interval: int = 3) -> None:
    start_time = time.time()
    while True:
        status = job.status()
        if status == 1:
            return
        if status == 2:
            raise RuntimeError("EMT job failed")
        if time.time() - start_time > timeout:
            raise TimeoutError("EMT job timed out")
        time.sleep(interval)


def find_fault_study_components(model):
    components = model.getAllComponents()
    fault = next(component for component in components.values() if getattr(component, "definition", None) == FAULT_DEFINITION)
    voltage_channel = next(
        component for component in components.values()
        if getattr(component, "definition", None) == CHANNEL_DEFINITION and component.args.get("Name") == VOLTAGE_CHANNEL_NAME
    )
    emt_job = next(job for job in model.jobs if job["rid"] == EMT_JOB_RID)
    return fault, voltage_channel, emt_job


def find_voltage_output_group(emt_job, channel_id):
    for index, group in enumerate(emt_job["args"]["output_channels"]):
        if channel_id in group.get("4", []):
            return index, group
    raise KeyError(f"Output group not found for channel {channel_id}")


def prepare_fault_study_model(model, *, fault_end_time, fault_chg, sampling_freq=2000):
    working_model = Model(deepcopy(model.toJSON()))
    fault, voltage_channel, emt_job = find_fault_study_components(working_model)
    _, output_group = find_voltage_output_group(emt_job, voltage_channel.id)
    working_model.updateComponent(
        fault.id,
        args={
            "fs": {"source": "2.5", "傻exp": ""},
            "fe": {"source": str(fault_end_time), "傻exp": ""},
            "chg": {"source": str(fault_chg), "傻exp": ""}
        }
    )
    working_model.updateComponent(
        voltage_channel.id,
        args={**voltage_channel.args, "Freq": {"source": str(sampling_freq), "傻exp": ""}}
    )
    output_group["1"] = int(sampling_freq)
    return working_model


def trace_window_rms(trace, start_time, end_time):
    samples = [value for time_value, value in zip(trace["x"], trace["y"]) if start_time <= time_value <= end_time]
    if not samples:
        raise ValueError(f"No samples in window {start_time}..{end_time}")
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def extract_voltage_recovery_metrics(result, trace_name=VOLTAGE_TRACE_NAME):
    plot_index = None
    for candidate_index, _plot in enumerate(result.getPlots()):
        candidate_names = result.getPlotChannelNames(candidate_index)
        if trace_name in candidate_names:
            plot_index = candidate_index
            break
    if plot_index is None:
        raise KeyError(f"Trace not found: {trace_name}")
    trace = result.getPlotChannelData(plot_index, trace_name)
    return {
        "trace_name": trace_name,
        "point_count": len(trace["x"]),
        "prefault_rms": trace_window_rms(trace, *PREFAULT_WINDOW),
        "fault_rms": trace_window_rms(trace, *FAULT_WINDOW),
        "postfault_rms": trace_window_rms(trace, *POSTFAULT_WINDOW),
        "late_recovery_rms": trace_window_rms(trace, *LATE_RECOVERY_WINDOW)
    }


def build_study_specs():
    return [
        {"name": "baseline", "fault_end_time": "2.7", "fault_chg": "0.01", "sampling_freq": 2000},
        {"name": "delayed_clearing", "fault_end_time": "2.9", "fault_chg": "0.01", "sampling_freq": 2000},
        {"name": "mild_fault", "fault_end_time": "2.7", "fault_chg": "1e4", "sampling_freq": 2000}
    ]


def run_fault_study(model):
    results = []
    for spec in build_study_specs():
        working_model = prepare_fault_study_model(
            model,
            fault_end_time=spec["fault_end_time"],
            fault_chg=spec["fault_chg"],
            sampling_freq=spec["sampling_freq"]
        )
        job = working_model.runEMT()
        wait_for_completion(job)
        results.append({**spec, "metrics": extract_voltage_recovery_metrics(job.result)})
    return results
