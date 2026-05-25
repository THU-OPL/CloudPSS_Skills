---
name: power-quality-analysis
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行真实 EMT 仿真，读取电压/电流波形并综合评估电能质量指标，包括 THD、单次谐波含量、电压暂降/暂升、三相不平衡、直流偏置和闪变代理指标，导出 JSON、CSV 和 Markdown 报告。当用户需要电能质量分析、电压暂降、三相不平衡、谐波综合评估、PCC 波形质量初筛或 EMT 波形质量报告时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
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
  entrypoint: scripts/verify_power_quality_analysis.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_power_quality_analysis
---

# Power Quality Analysis

## When to use

- 需要从 CloudPSS EMT 波形中做电能质量综合初筛。
- 需要在同一次 EMT 结果中同时计算谐波、暂降/暂升、不平衡、直流偏置和闪变代理指标。
- 需要对 `vac:0`、`vac:1`、`vac:2` 这类三相瞬时电压通道生成质量报告。
- 需要轻量、独立的 EMT 波形分析 skill，而不是依赖共享 PSA 包或其他 skill。

## Input contract

接受用户直接提供的等价 JSON 配置；如果未指定通道，runtime 会从 EMT 结果中自动选择少量电压样通道。三相不平衡建议显式传入 `three_phase`。

- `analysis`
  - `fundamental_freq`: 基波频率，默认 `50.0` Hz。
  - `max_harmonic`: 最高谐波次数，默认 `25`。
  - `analysis_window`: THD、不平衡、直流偏置和闪变分析时间窗 `[start, end]`；默认取仿真末段。
  - `event_window`: 暂降/暂升搜索窗口 `[start, end]`；默认使用全仿真时间。
  - `reference_window`: 暂降/暂升参考 RMS 计算窗口 `[start, end]`；默认取 `event_window` 开始后的短窗口。
  - `cycle_samples`: 滑动 RMS 窗口点数；默认按采样率和基波周期自动估计。
  - `min_samples`: 单通道最小样本数，默认 `128`。
  - `limits`: 指标阈值，支持 `thd_percent`、`single_harmonic_percent`、`voltage_dip_percent`、`voltage_swell_percent`、`unbalance_percent`、`dc_offset_percent`、`flicker_proxy_percent`。
- `channels`
  - `voltage`: 单相或相电压通道列表。
  - `current`: 电流通道列表，按同样方式计算谐波和直流偏置。
  - `generic`: 通用波形通道列表。
  - `three_phase`: 三相组列表，例如 `{"name": "PCC", "a": "vac:0", "b": "vac:1", "c": "vac:2"}`。
  - `auto_max_channels`: 未指定通道时自动选择最大通道数，默认 `3`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。
  - `export_harmonics`: 是否生成谐波明细 CSV。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝 `model/holdme/*` 和公开占位 RID 作为 live verification 来源。
3. 调用真实 CloudPSS `runEMT()` 并轮询到完成。
4. 从 `job.result` 中定位显式配置或自动选择的波形通道。
5. 对单通道计算 RMS、基波、THD、最大单次谐波、暂降/暂升、直流偏置和闪变代理指标。
6. 对显式三相组计算各相 RMS、最大相偏差不平衡和基波序分量负序/正序不平衡。
7. 按配置阈值生成 `violations` 和 `overall_status`。
8. 导出 JSON、指标 CSV、谐波明细 CSV 和 Markdown 报告。

## Output

- CloudPSS job id。
- 每个单通道的 `rms`、`fundamental_rms`、`thd_percent`、`max_single_harmonic_percent`、`dip_percent`、`swell_percent`、`dc_offset_percent` 和 `flicker_proxy_percent`。
- 每个三相组的 `rms_unbalance_percent`、`sequence_unbalance_percent` 和各相 RMS。
- `summary.channel_count`、`summary.three_phase_group_count`、`summary.max_thd_percent`、`summary.max_voltage_dip_percent`、`summary.max_unbalance_percent`、`summary.violation_count` 和 `summary.overall_status`。
- JSON、CSV、谐波 CSV 和 Markdown 产物路径。

## Constraints

- 该 skill 不创建扰动，不修改云端模型，只分析已有 EMT 输出通道。
- 当前闪变为短窗口 RMS 调制代理指标，不是 IEC 61000-4-15 正式 Pst/Plt。
- 当前暂降/暂升为基于滑动 RMS 的事件初筛，参考电压依赖 `reference_window`。
- 当前谐波计算使用目标频点投影，适合 EMT 波形初筛，不替代正式电能质量合规报告。
- 如果目标通道不存在、分析时间窗无数据、样本数不足或 EMT 仿真失败，验证脚本直接失败。

## Live verification

- 验证日期：`2026-05-25`
- 验证模型：`model/CloudPSS/IEEE3`
- EMT job id：`68ae0491-3a9e-487f-a18c-6142a367b925`
- 验证通道：`vac:0`、`vac:1`、`vac:2`
- 验证三相组：`{"name": "vac", "a": "vac:0", "b": "vac:1", "c": "vac:2"}`
- 验证摘要：3 个电压通道和 1 个三相组成功分析；最大 THD 约 `0.025625%`，最大电压暂降约 `83.074393%`，最大电压暂升约 `73.588521%`，最大三相不平衡约 `0.006939%`。
- 默认阈值下 `overall_status` 为 `VIOLATION`，违规来自验证窗口包含 `IEEE3` 启动/扰动阶段的暂降、暂升和闪变代理指标；THD 和三相不平衡指标未越限。
- 验证产物：
  - `results/skill-verification/power-quality-analysis/power_quality_analysis_20260525_080056.json`
  - `results/skill-verification/power-quality-analysis/power_quality_analysis_20260525_080056.csv`
  - `results/skill-verification/power-quality-analysis/power_quality_analysis_harmonics_20260525_080056.csv`
  - `results/skill-verification/power-quality-analysis/power_quality_analysis_report_20260525_080056.md`

## Verified script

- `skills/power-quality-analysis/scripts/verify_power_quality_analysis.py`
