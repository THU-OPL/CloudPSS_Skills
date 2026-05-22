---
name: frequency-response-analysis
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行真实 EMT 仿真，读取频率或转速通道，计算初值、最低/最高值、最大偏差、RoCoF、稳态值、稳定时间和阈值结论，并导出 JSON、CSV 和 Markdown 报告。当用户需要频率响应、转速响应、RoCoF、频率最低点、扰动后恢复时间或一次调频响应初筛时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
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
  entrypoint: scripts/verify_frequency_response_analysis.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_frequency_response_analysis
---

# Frequency Response Analysis

## When to use

- 需要从 CloudPSS EMT 波形中评估频率或转速响应。
- 需要计算频率最低点、最高点、最大偏差、RoCoF、稳态值和恢复时间。
- 需要对 `#wr1:0`、`#wr2:0`、`#wr3:0` 这类标幺转速通道换算为 Hz。
- 需要轻量、独立的 EMT 波形分析 skill，而不是依赖共享 PSA 包或其他 skill。

## Input contract

接受用户直接提供的等价 JSON 配置；如果未指定通道，runtime 会从 EMT 结果中自动选择包含 `wr`、`freq` 或 `speed` 的少量通道。

- `analysis`
  - `base_frequency_hz`: 基准频率，默认 `50.0` Hz。
  - `analysis_window`: 分析时间窗 `[start, end]`；默认使用全仿真时间。
  - `initial_window`: 初值计算窗口 `[start, end]`；默认取分析窗开始后的短窗口。
  - `steady_window`: 稳态值计算窗口 `[start, end]`；默认取分析窗末段窗口。
  - `settling_threshold_hz`: 稳定阈值，默认 `0.05` Hz。
  - `rocof_window_samples`: RoCoF 平滑窗口点数，默认 `5`。
  - `min_samples`: 单通道最小样本数，默认 `128`。
- `channels`
  - `frequency`: 已是 Hz 的频率通道。
  - `speed_pu`: 标幺转速通道，按 `base_frequency_hz` 换算为 Hz。
  - `generic`: 通用通道，默认按标幺转速处理。
  - `auto_max_channels`: 未指定通道时自动选择最大通道数，默认 `3`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝 `model/holdme/*` 和公开占位 RID 作为 live verification 来源。
3. 调用真实 CloudPSS `runEMT()` 并轮询到完成。
4. 从 `job.result` 中定位目标频率/转速通道。
5. 将标幺转速通道换算为 Hz，并截取分析时间窗。
6. 计算初值、最低/最高频率、最大正/负偏差、最大 RoCoF、稳态值、稳态偏差和稳定时间。
7. 导出 JSON、CSV 和 Markdown 报告。

## Output

- CloudPSS job id。
- 每个通道的 `sample_count`、`initial_frequency_hz`、`min_frequency_hz`、`max_frequency_hz`。
- `max_abs_deviation_hz`、`max_rocof_hz_per_s`、`steady_frequency_hz`、`settling_time_s`。
- `summary.max_abs_deviation_hz`、`summary.max_rocof_hz_per_s` 和 `summary.pass_settling_threshold`。
- JSON、CSV 和 Markdown 产物路径。

## Live verification

- Verified on `model/CloudPSS/IEEE3`.
- Verified EMT job id: `63f4d2ec-1478-426d-8202-061fb097b238`.
- Verified channels: `#wr1:0`, `#wr2:0`, `#wr3:0`.
- Verified output summary: 3 speed channels analyzed, max absolute frequency deviation about `0.217181 Hz`, max RoCoF about `4.657117 Hz/s`, all channels settled within the default `0.05 Hz` threshold.
- Verified artifacts:
  - `results/skill-verification/frequency-response-analysis/frequency_response_analysis_20260521_161228.json`
  - `results/skill-verification/frequency-response-analysis/frequency_response_analysis_20260521_161228.csv`
  - `results/skill-verification/frequency-response-analysis/frequency_response_analysis_report_20260521_161228.md`

## Constraints

- 该 skill 不创建扰动，不修改云端模型，只分析已有 EMT 输出通道。
- 当前指标是从波形计算的频率响应初筛，不替代完整频率稳定或调频控制专题研究。
- 如果目标通道不存在、分析时间窗无数据、样本数不足或 EMT 仿真失败，验证脚本直接失败。
- 默认只分析少量通道，避免生成过大的本地产物。

## Verified script

- `skills/frequency-response-analysis/scripts/verify_frequency_response_analysis.py`
