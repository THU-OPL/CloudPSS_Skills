---
name: short-circuit-analysis
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行真实 EMT 仿真，读取电流通道或功率/电压等效通道，计算峰值电流、故障窗口 RMS、故障前/后 RMS、直流偏置估计、短路容量近似值，并导出 JSON、CSV 和 Markdown 报告。当用户需要短路电流、故障电流、短路容量、断路器开断电流水平、保护整定初筛或已有短路场景的 EMT 波形分析时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Set CLOUDPSS_TEST_EMT_MODEL_RID or pass an EMT-ready model RID. Verification uses model/CloudPSS/IEEE3 and refuses placeholder or model/holdme/* sources.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_short_circuit_analysis.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_short_circuit_analysis
---

# Short Circuit Analysis

## When to use

- 需要从 CloudPSS EMT 波形中评估短路电流或故障电流。
- 需要计算峰值电流、故障窗口 RMS、故障前/后 RMS、短路容量近似值。
- 需要基于已有短路/故障场景输出保护整定或设备开断电流水平的初筛报告。
- 需要轻量、独立的 EMT 波形分析 skill，而不是依赖共享 PSA 包或其他 skill。

## Input contract

接受用户直接提供的等价 JSON 配置；如果未指定通道，runtime 会优先自动选择看起来像电流的通道。若模型没有电流通道，可以用 `equivalent_pairs` 指定功率/电压通道，按三相公式估算等效电流。

- `analysis`
  - `base_voltage_kv`: 基准线电压，默认 `230.0` kV，用于 `Ssc = sqrt(3) * V(kV) * I(kA)`。
  - `current_scale`: 电流通道缩放系数，默认 `1.0`。
  - `power_scale_mw`: 功率通道缩放系数，默认 `1.0`，用于等效电流估算。
  - `voltage_scale_pu`: 电压通道缩放系数，默认 `1.0`。
  - `nominal_voltage_pu`: 等效估算时电压过低的回退标幺值，默认 `1.0`。
  - `analysis_window`: 总分析时间窗 `[start, end]`；默认使用全仿真时间。
  - `prefault_window`: 故障前窗口 `[start, end]`；默认取分析窗前段。
  - `fault_window`: 故障窗口 `[start, end]`；默认取分析窗中段。
  - `postfault_window`: 故障后窗口 `[start, end]`；默认取分析窗末段。
  - `min_samples`: 单通道最小样本数，默认 `128`。
- `channels`
  - `current`: 真实电流通道列表，优先使用。
  - `voltage`: 电压波形通道列表，可作为普通波形统计。
  - `generic`: 通用波形通道列表。
  - `equivalent_pairs`: 功率/电压通道对列表，例如 `{"power": "#P1:0", "voltage": "vac:0"}`。
  - `auto_max_channels`: 未指定通道时自动选择最大通道数，默认 `3`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝 `model/holdme/*` 和公开占位 RID 作为 live verification 来源。
3. 调用真实 CloudPSS `runEMT()` 并轮询到完成。
4. 从 `job.result` 中定位目标电流通道；若无电流通道，则按 `equivalent_pairs` 读取功率和电压通道。
5. 截取分析、故障前、故障中、故障后窗口，校验时间轴单调和样本数。
6. 计算峰值电流、故障窗口 RMS、故障前/后 RMS、RMS 比值、直流偏置估计和短路容量近似值。
7. 导出 JSON、CSV 和 Markdown 报告。

## Output

- CloudPSS job id。
- 每个通道的 `sample_count`、`peak_current`、`fault_rms_current`、`prefault_rms_current`、`postfault_rms_current`。
- 每个通道的 `short_circuit_mva`、`fault_to_prefault_rms_ratio`、`postfault_to_prefault_rms_ratio`。
- `summary.max_peak_current`、`summary.max_fault_rms_current`、`summary.max_short_circuit_mva` 和 `summary.methods`。
- JSON、CSV 和 Markdown 产物路径。

## Live verification

- Verified on `model/CloudPSS/IEEE3`.
- Verified EMT job id: `57d37433-7b5f-40d7-aa2f-852bfe0919c4`.
- Verified channels: `#P1:0|vac:0`, `#P2:0|vac:1`, `#P3:0|vac:2`.
- Verified output summary: 3 equivalent-current channels analyzed, max fault RMS current about `0.003232` (scaled from power/voltage traces), max short-circuit capacity about `1.287425 MVA`, all channels used `estimated_from_power_voltage`.
- Verified artifacts:
  - `results/skill-verification/short-circuit-analysis/short_circuit_analysis_20260521_163708.json`
  - `results/skill-verification/short-circuit-analysis/short_circuit_analysis_20260521_163708.csv`
  - `results/skill-verification/short-circuit-analysis/short_circuit_analysis_report_20260521_163708.md`

## Constraints

- 该 skill 默认不创建故障、不修改云端模型，只分析已有 EMT 输出通道。
- 如果模型没有真实电流通道，`equivalent_pairs` 只能给出基于功率/电压的等效电流和短路容量近似值，输出会标记 `estimated_from_power_voltage`。
- 当前指标是短路电流初筛，不替代 IEC 60909 或设备校核级短路计算。
- 如果目标通道不存在、分析时间窗无数据、样本数不足或 EMT 仿真失败，验证脚本直接失败。

## Verified script

- `skills/short-circuit-analysis/scripts/verify_short_circuit_analysis.py`
