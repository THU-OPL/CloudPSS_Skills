---
name: harmonic-analysis
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行真实 EMT 仿真，读取目标 plot/channel 波形，在指定时间窗内计算基波、各次谐波幅值、THD、RMS 和限值结论，并导出 JSON、CSV 和 Markdown 报告。当用户需要 EMT 波形 FFT、谐波含量、THD、谐波谱或电能质量初筛时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Set CLOUDPSS_TEST_EMT_MODEL_RID or pass an EMT-ready model RID under your own account. Verification refuses placeholder and model/holdme/* sources.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_harmonic_analysis.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_harmonic_analysis
---

# Harmonic Analysis

## When to use

- 需要对 CloudPSS EMT 波形做谐波分析或 THD 初筛。
- 需要从真实 `runEMT()` 结果读取电压、电流或任意目标通道。
- 需要在指定稳态时间窗内输出基波幅值、各次谐波含量和 THD。
- 需要轻量、独立的 EMT 波形分析 skill，而不是依赖共享 PSA 包或其他 skill。

## Input contract

接受用户直接提供的等价 JSON 配置；如果没有提供通道，runtime 会从 EMT 结果的前几个可读通道中自动选择少量通道。

- `analysis`
  - `fundamental_freq`: 基波频率，默认 `50.0` Hz。
  - `max_harmonic`: 最高谐波次数，默认 `25`。
  - `thd_limit_percent`: THD 阈值，默认 `5.0`。
  - `analysis_window`: 分析时间窗 `[start, end]`，默认取仿真末段窗口。
  - `min_samples`: 单通道最小样本数，默认 `128`。
- `channels`
  - `voltage`: 可选电压通道名列表。
  - `current`: 可选电流通道名列表。
  - `generic`: 可选通用通道名列表。
  - `auto_max_channels`: 未指定通道时自动选择的最大通道数，默认 `3`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。
  - `export_spectrum`: 是否导出长表 CSV 频谱。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝 `model/holdme/*` 和公开占位 RID 作为 live verification 来源。
3. 调用真实 CloudPSS `runEMT()` 并轮询到完成。
4. 从 `job.result` 中定位目标通道；如果用户未指定，则自动选择少量可读通道。
5. 在分析时间窗内截取 `x/y` 样本并校验时间轴单调、样本数足够。
6. 对每个目标通道计算 DC、RMS、基波幅值、2..N 次谐波幅值、各次谐波百分比和 THD。
7. 导出 JSON、CSV、可选频谱 CSV 和 Markdown 报告。

## Output

- CloudPSS job id。
- 每个通道的 `sample_count`、`sampling_rate_hz`、`dc_component`、`rms`。
- 每个通道的 `fundamental`、`harmonics` 和 `thd_percent`。
- `summary.max_thd_percent`、`summary.thd_violations` 和 `summary.pass_thd_limit`。
- JSON、CSV、频谱 CSV 和 Markdown 产物路径。

## Live verification

- Verified on `model/CloudPSS/IEEE3`.
- Verified EMT job id: `d7676987-4cb3-467c-8db5-af81f4a04a9f`.
- Verified channels: `vac:0`, `vac:1`, `vac:2`.
- Verified output summary: 3 voltage channels analyzed, max THD about `0.530124%`, no THD violations at the default `5%` threshold.

## Constraints

- 该 skill 不创建新的量测元件，不修改云端模型，只分析已有 EMT 输出通道。
- 当前使用标准库在目标频点计算谐波幅值；适合工程初筛，不替代正式电能质量合规报告。
- 如果目标通道不存在、分析时间窗无数据、样本数不足或 EMT 仿真失败，验证脚本直接失败。
- 默认只分析少量通道，避免生成过大的本地产物。

## Verified script

- `skills/harmonic-analysis/scripts/verify_harmonic_analysis.py`
