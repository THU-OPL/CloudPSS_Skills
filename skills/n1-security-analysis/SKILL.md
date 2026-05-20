---
name: n1-security-analysis
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 对 CloudPSS 模型执行单次 N-1 暂态安全校核。当前已验证流程基于随机 N-1 故障、母线电压 Vrms、发电机功率 PT_o、转速 wr_o 和功角 theta_o 的量测配置，然后运行电磁暂态仿真并提取 check_result。当用户提到 N-1 安全校核、单次故障校核、暂态安全检查、故障后电压/频率/功角检查时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Uses the versioned cloudpss-psa-core shared package; verified workflow submits a real EMT job.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_n1_security.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# N-1 Security Analysis

## 何时使用

- 需要对 CloudPSS 模型执行单次 N-1 故障暂态安全校核。
- 需要生成一次随机 N-1 故障并检查电压、频率、功角结果。
- 需要返回 `extract_and_check_data` 的结构化检查结果，而不是只看波形图。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`。
- 默认验证模型为 `model/CloudPSS/IEEE39`。
- 运行时依赖 `cloudpss-psa-core` 提供的 `psa.tool_box.PowerSystemAnalysis`。

## 已验证工作流

1. `initModelAndCreateSACanvas(cloudpss_model="model/CloudPSS/IEEE39")`
2. `power_flow_sample_simple_ramdom(flowJobName="SA_潮流计算", flowConfigname="SA_参数方案", P_low=1.0, P_high=1.0)`
3. `generate_random_fault_params_set_N_1()`
4. 依次调用 `addComponentOutputMeasures` 挂 4 组量测：
   `model/CloudPSS/_newBus_3p` + `Vrms`
   `model/CloudPSS/SyncGeneratorRouter` + `PT_o`
   `model/CloudPSS/SyncGeneratorRouter` + `wr_o`
   `model/CloudPSS/SyncGeneratorRouter` + `theta_o`
5. `runProject(jobName="SA_电磁暂态仿真", configName="SA_参数方案", showLogs=False)`
6. `extract_and_check_data(jobName="SA_电磁暂态仿真", transKey=..., fault_start_time=..., cut_time=..., fault_type_index=...)`

## 结果格式

- `generate_random_fault_params_set_N_1`
  返回 `result`、`transKey`、`side`、`fault_start_time`、`cut_time`、`fault_type_index`
- `extract_and_check_data`
  返回 `fault_info`、`check_result`、`plotly_result`、`plot_export_errors`
- `check_result`
  包含 `voltage_ok`、`min_voltage`、`frequency_ok`、`max_freq_deviation`、`power_angle_ok`、`max_power_angle_diff`

## 重要约束

- 当前已验证频率检查流程使用 `SyncGeneratorRouter.wr_o`，不是 `addBusFrequencyMonitors`。
- `frequency_ok` 为 `False` 仍然是有效分析结果，表示该故障场景频率不满足阈值，不代表流程失败。
- `plot_export_errors` 可能因本地图像导出环境问题非空；只要 `check_result` 成功返回，主分析链仍视为完成。
- 当前 skill 只写入已验证的随机单次 N-1 工作流。指定线路的手动 `setN_1_GroundFault` 流程不在本技能的已验证闭环内。

## 已验证脚本

- Python 直调版：`skills/n1-security-analysis/scripts/verify_n1_security.py`

该脚本于 `2026-03-26` 基于真实 CloudPSS 仿真完成验证。

