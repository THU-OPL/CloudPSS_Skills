---
name: waveform-export
description: 使用 CloudPSS SDK 对真实 EMT 仿真结果提取 plot/channel 波形，并导出为 CSV 或 JSON，同时校验时间轴、采样点数和通道数据完整性。当用户需要导出 EMT 波形、保存 CloudPSS 仿真通道数据、筛选时间范围、为 COMTRADE 或结果对比准备数据文件时使用。
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
  category: export
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_waveform_export.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_waveform_export
---

# Waveform Export

## When to use

- 需要从 CloudPSS EMT 仿真结果导出时域波形。
- 需要把 plot/channel 数据保存为 CSV 或 JSON。
- 需要筛选目标 plot、目标通道或时间范围。
- 需要为 `comtrade-export`、`result-compare-and-visualization` 或报告生成提供本地波形数据。

## Workflow

1. 加载 token 和 EMT-ready 模型；公开使用时通过 `CLOUDPSS_TEST_EMT_MODEL_RID` 或命令行传入自己账号下的模型 RID。
2. 拒绝 `model/holdme/...` 验证源。
3. 调用 `runEMT()` 执行真实 CloudPSS EMT 仿真。
4. 遍历 `job.result.getPlots()` 和 `getPlotChannelNames()`。
5. 使用 `getPlotChannelData(plot_index, channel_name)` 读取 `x/y` 数据。
6. 根据 plot、channel 和时间范围筛选数据。
7. 导出 CSV 或 JSON，并校验导出文件非空、时间轴单调递增、样本值非空。

## Output

- CloudPSS job id 和 plot/channel 摘要。
- 导出的 CSV/JSON 文件路径。
- 每个导出通道的样本点数、时间范围和值范围。

## Constraints

- 该 skill 只导出已存在的 CloudPSS 仿真结果通道，不创建新测量元件。
- 如果模型没有 EMT topology、仿真失败或目标通道不存在，验证脚本直接失败。
- 默认验证只导出少量通道，避免生成过大的仓库产物。
- 如果账号下没有 IEEE3 EMT 样例，先从官方 `model/CloudPSS/IEEE3` 保存或构建到自己账号，再传入该新 RID；本仓库实测使用的是私有 EMT-ready 副本，不作为公开默认值。

## Verified script

- `skills/waveform-export/scripts/verify_waveform_export.py`
