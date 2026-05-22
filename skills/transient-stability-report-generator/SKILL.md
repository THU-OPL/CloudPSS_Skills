---
name: transient-stability-report-generator
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行真实 EMT 仿真，读取转速、频率、电压、功率或功角通道，计算暂态稳定筛查指标，并生成 JSON、CSV 和 Markdown 工程报告。当用户需要暂态稳定报告、故障后转速/电压恢复摘要、RoCoF、转速偏差、阻尼/振荡初筛、关键波形指标表或可归档的 EMT 稳定性报告时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
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
  entrypoint: scripts/verify_transient_stability_report_generator.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_transient_stability_report
---

# Transient Stability Report Generator

## When to use

- 需要从真实 CloudPSS EMT 波形生成暂态稳定筛查报告。
- 需要汇总发电机转速、频率、母线电压、功率或功角通道的关键指标。
- 需要输出执行摘要、稳定性结论、关键指标表和后续建议。
- 需要轻量、独立的报告型 skill，而不是跨 skill 编排器或共享 PSA 包工作流。

## Input contract

接受用户直接提供的等价 JSON 配置；如果未指定通道，runtime 会自动选择少量转速、电压、功率或功角通道。

- `report`
  - `title`: 报告标题，默认 `Transient Stability Screening Report`。
  - `scenario`: 场景描述，默认 `existing EMT scenario`。
  - `author`: 报告作者信息，默认 `CloudPSS agent skill`。
- `assessment`
  - `base_frequency_hz`: 基准频率，默认 `50.0` Hz。
  - `analysis_window`: 总分析时间窗 `[start, end]`；默认使用全仿真时间。
  - `prefault_window`: 故障前或初始窗口 `[start, end]`；默认取分析窗前段。
  - `postfault_window`: 故障后或稳态窗口 `[start, end]`；默认取分析窗末段。
  - `settling_threshold_pu`: 转速/频率进入稳态的阈值，默认 `0.002` pu。
  - `max_speed_deviation_pu`: 转速/频率最大偏差阈值，默认 `0.02` pu。
  - `rocof_window_samples`: RoCoF 平滑窗口点数，默认 `5`。
  - `voltage_low_limit_pu`: 电压最低值阈值，默认 `0.8` pu。
  - `voltage_recovery_limit_pu`: 稳态恢复电压阈值，默认 `0.9` pu。
  - `assess_voltage_channels`: 是否把 `channels.voltage` 当作标幺/RMS 电压参与恢复判据，默认 `false`。
  - `min_samples`: 单通道最小样本数，默认 `128`。
- `channels`
  - `speed_pu`: 标幺转速通道，如 `#wr1:0`。
  - `frequency`: Hz 频率通道；runtime 会按 `base_frequency_hz` 换算为 pu 评估。
  - `voltage_pu`: 明确为标幺/RMS 的电压通道，会参与电压恢复判据。
  - `voltage`: 电压波形通道；默认作为支撑波形写入报告，不参与 pu 电压恢复判据。
  - `power`: 有功功率通道，作为支撑波形进入报告，不参与稳定/失稳布尔判据。
  - `angle`: 功角通道，作为支撑波形进入报告。
  - `generic`: 通用通道，作为支撑波形进入报告。
  - `auto_max_channels`: 未指定通道时每类自动选择最大通道数，默认 `3`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝 `model/holdme/*` 和公开占位 RID 作为 live verification 来源。
3. 调用真实 CloudPSS `runEMT()` 并轮询到完成。
4. 从 `job.result` 定位目标转速、电压、功率、功角或通用通道。
5. 截取分析窗口、初始窗口和末段稳态窗口，校验时间轴单调和样本数。
6. 对转速/频率通道计算最大偏差、RoCoF、稳定时间、振荡频率和阻尼估计。
7. 对 `voltage_pu` 通道计算最低电压、稳态恢复值和恢复判据；普通 `voltage` 通道默认只作为支撑波形。
8. 对功率/功角/通用通道计算支撑统计，放入报告但不单独给出稳定判定。
9. 生成 JSON、CSV 和 Markdown 报告。

## Output

- CloudPSS job id。
- `summary.overall_assessment`、`assessed_channel_count`、`unstable_channel_count`。
- `summary.max_speed_deviation_pu`、`summary.max_rocof_hz_per_s`、`summary.min_voltage_pu`。
- 每个通道的 `assessment_type`、`is_stable`、`initial_value`、`min_value`、`max_value`、`steady_value`、`max_abs_deviation`、`settling_time_s`。
- Markdown 报告包含执行摘要、关键指标表、工程说明和后续建议。

## Live verification

- Verified on `model/CloudPSS/IEEE3`.
- Verified EMT job id: `c945ea49-1797-46a9-9f64-2ab2b7628860`.
- Verified assessed channels: `#wr1:0`, `#wr2:0`, `#wr3:0`.
- Verified supporting channels: `vac:0`, `vac:1`, `vac:2`, `#P1:0`, `#P2:0`, `#P3:0`.
- Verified output summary: 9 channels included, 3 rotor-speed channels assessed, overall assessment `stable_by_configured_criteria`, max speed deviation about `0.004344 pu`, max RoCoF about `4.657117 Hz/s`.
- Verified artifacts:
  - `results/skill-verification/transient-stability-report-generator/transient_stability_report_20260522_094740.json`
  - `results/skill-verification/transient-stability-report-generator/transient_stability_report_20260522_094740.csv`
  - `results/skill-verification/transient-stability-report-generator/transient_stability_report_report_20260522_094740.md`

## Constraints

- 该 skill 不创建故障、不修改云端模型，只分析已有 EMT 输出通道并生成报告。
- 当前稳定性结论是波形初筛：转速/频率按最大偏差和稳定时间判断，明确的 `voltage_pu` 通道按最低值和稳态恢复判断。
- 对 `vac:*` 这类瞬时电压通道，不要默认套用 pu/RMS 电压恢复阈值；如用户确认其单位已归一化，可设置 `assess_voltage_channels=true`。
- 功率、功角和通用通道默认作为支撑波形，不直接替代正式功角稳定判据。
- 如果目标通道不存在、分析时间窗无数据、样本数不足或 EMT 仿真失败，验证脚本直接失败。

## Verified script

- `skills/transient-stability-report-generator/scripts/verify_transient_stability_report_generator.py`
