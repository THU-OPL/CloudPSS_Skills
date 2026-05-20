---
name: disturbance-severity-analysis
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis，对 CloudPSS 电力系统模型执行单次扰动后的电压严重度分析，自动完成随机工况、N-1 故障、电压测量、DV/SI 计算、DUDV 导出和结论保存。用于用户提到扰动严重度、DV、SI、电压恢复、故障后电压评估或 DUDV 曲线时；当用户提出采样频率、监测母线、仿真时长、DV/SI 判据等专业要求时，也用于专家模式分析。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Uses the versioned cloudpss-psa-core shared package; do not import the old psa repository directly.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_disturbance_severity.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# Disturbance Severity Analysis

优先使用 `run_disturbance_severity_analysis`。不要默认拆成多步调用，除非用户明确要求逐步执行、定位故障、或调整底层专业参数。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`。
- 当前验证模型为 `model/CloudPSS/IEEE39`。
- 运行时依赖 `cloudpss-psa-core` 提供的 `psa.tool_box.PowerSystemAnalysis`。

## 默认模式

适用于非专家用户。只需要知道模型和大致分析目标。

- 默认 `analysis_mode=quick`
- 默认自动设置轻量 EMT 仿真规模
- 默认从当前算例母线的真实 `VBase` 中自动选择一个单一电压等级，不靠猜测
- 默认在该电压等级内优先选择故障附近的少量关键母线，并限制监测母线数量，避免输出通道过多
- 默认保存 `JSON / CSV / Markdown / 图表` 结果
- 默认返回一句可直接给用户展示的分析结论

默认模式下，优先只传这些输入：

- `cloudpss_model`
- 可选：`Keys`、`NameSet`、`VMin`、`VMax`

如果不传 `Keys / NameSet / VMin / VMax`，组合工具会自动：

1. 统计模型内所有母线的真实电压等级
2. 选择母线数量最多的单一电压等级作为默认监测等级
3. 围绕随机故障线路或变压器优先挑选少量关键母线
4. 返回 `bus_selection` 说明本次自动选择了哪个电压等级以及选中了哪些母线

## 专家模式

当用户明确要求更专业控制时，再显式传入这些参数：

- 规模与性能：`analysis_mode`、`freq`、`MaxCount`、`emt_end_time`、`n_cpu`、`n_ele_cpu`
- 监测范围：`Keys`、`NameSet`、`VMin`、`VMax`
- DV 判据：`dv_judge`、`dv_vmin_recovery_ratio`、`dv_vmax_recovery_ratio`
- SI 判据：`si_tinterval`、`si_window`、`si_stage1_threshold`、`si_stage2_threshold`

这些参数的含义和结果解释见 `references/parameters-and-results.md`。

## 输出约定

组合工具会返回并保存：

- 故障信息：`fault_context`
- 监测母线：`screened_bus`、`bus_labels`
- 母线筛选说明：`bus_selection`
- 每母线摘要：`per_bus_summary`
- 指标结果：`dv_result`、`si_result`
- 图形结果：`dudv_plot`、`artifacts.dv_margin_chart`
- 保存文件：`artifacts.summary_json`、`artifacts.summary_csv`、`artifacts.summary_markdown`
- 结论：`severity_level`、`analysis_conclusion`

## 推荐调用顺序

1. 优先调用 `run_disturbance_severity_analysis`
2. 如果用户要求排查过程，再使用回退工作流：`initModelAndCreateSACanvas -> createOrUpdateJob -> power_flow_sample_simple_ramdom -> generate_random_fault_params_set_N_1 -> addVoltageMeasures -> runProject -> calculateDV -> calculateSI -> draw_DUDV`
3. 长耗时任务结束后，如果还要继续同一会话中的别的分析，必要时调用 `clear_runtime_state`

## 何时回退到底层工具

只有在这些场景下才拆分工具链：

- 用户要精确控制故障或仿真步骤
- 用户要分别观察潮流、故障设置、波形输出配置
- 需要单独重算 `calculateDV` 或 `calculateSI`
- 需要定位某一步的仿真失败原因

## 验证脚本

- Python 直调：`skills/disturbance-severity-analysis/scripts/verify_disturbance_severity.py`
- 评测定义：`skills/disturbance-severity-analysis/evals/evals.json`

