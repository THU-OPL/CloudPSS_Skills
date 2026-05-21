---
name: fault-scenario-editor
description: 使用 CloudPSS SDK 巡检真实模型 revision，识别故障元件与量测通道，并生成可供 `emt_fault_study`、`fault_clearing_scan`、`fault_severity_scan` 复用的标准化故障场景蓝图。当用户需要先统一故障场景定义、提取场景参数模板、导出故障研究 manifest，而不直接运行 EMT 仿真时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Supports `.cloudpss_token` fallback for local verification, but live verification still uses an EMT-ready model under your own account.
metadata:
  owner: cloudpss-team
  category: workflow
  visibility: internal
  maturity: experimental
  entrypoint: scripts/verify_fault_scenario_editor.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: real_cloudpss_model_inspection
---

# Fault Scenario Editor

## 何时使用

- 需要先从真实模型中统一故障场景定义。
- 需要在不运行 EMT 的前提下，整理故障研究蓝图。
- 需要把故障研究输入标准化给 `emt_fault_study`、`fault_clearing_scan` 或 `fault_severity_scan`。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`，或当前目录存在 `.cloudpss_token`。
- 默认模型使用 `CLOUDPSS_TEST_EMT_MODEL_RID`，公开使用时请传入你自己账号下的 EMT-ready 模型 RID。
- 模型中应至少包含一个 `_newFaultResistor_3p` 故障元件和一个 `_newChannel` 量测通道。

## 工作流

1. 加载真实模型或本地工作副本。
2. 巡检 component 库存，统计 bus / line / generator / fault / channel。
3. 选择故障元件锚点和量测通道锚点。
4. 生成标准化故障场景蓝图。
5. 导出 JSON 和 Markdown 结果。

## 输出

- 模型摘要
- 故障锚点与量测锚点
- 可复用的场景模板
- 下游 skill 输入契约

## 蓝图输出契约

这个 skill 输出 `fault-blueprint-v1` 风格的故障场景蓝图。下游 skill 可以使用这个蓝图，也可以接收用户提供的等价 JSON 配置；不要要求下游 import 本 skill 的代码。

核心字段：

- `fault_point`
  - `fault_bus`
  - `fault_type`
  - `fault_time`
  - `fault_duration`
  - `fault_resistance`
- `breaker_action`
  - `mode`
  - `trip_time`
  - `reclose_time`
  - `clearing_policy`
  - `clear_time`
- `scenario_templates`
  - `baseline`: `fs / fe / chg`
  - `delayed_clearing`: `fs / fe / chg`
  - `mild_fault`: `fs / fe / chg`
- `fault_clearing_scan`
  - `fault_point`
  - `breaker_action`
  - `scan.fs`
  - `scan.fe_values`
  - `scan.chg`
  - `assessment.trace_name`
  - `assessment.study_time`
- `fault_severity_scan`
  - `fault_point`
  - `breaker_action`
  - `scan.fs`
  - `scan.fe`
  - `scan.chg_values`
  - `assessment.trace_name`
  - `assessment.time_windows`

下游映射：

- `emt-fault-study`: 使用 `fault_point`、`breaker_action` 和 `scenario_templates.baseline / delayed_clearing / mild_fault`。
- `fault-clearing-scan`: 使用 `fault_clearing_scan` 模板。
- `fault-severity-scan`: 使用 `fault_severity_scan` 模板。

## 限制

- 不提交 EMT 任务。
- 不运行故障扫描。
- 不保存新的云端模型 revision。
- 默认不接受 `model/holdme/*` 作为 live verification 来源。
- 如果模型缺少故障元件或量测通道，构建会失败。

## 验证入口

- `scripts/verify_fault_scenario_editor.py`

## 备注

- 这个 skill 的定位是“场景编辑器”，不是“仿真执行器”。
- 它刻意不重复 `emt_fault_study`、`fault_clearing_scan`、`fault_severity_scan` 的计算逻辑，只输出它们可消费的标准输入蓝图。
