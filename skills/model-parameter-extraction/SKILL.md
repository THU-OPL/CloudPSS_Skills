---
name: model-parameter-extraction
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 从 CloudPSS 模型提取母线、线路、变压器、发电机、负荷、通道和潮流设置参数，并通过真实潮流仿真补充母线、支路、发电机运行结果。当用户需要导出模型参数、盘点设备参数、生成设备清册、对接外部分析或核对潮流输入数据时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: The verification script reads the real revision and runs CloudPSS power flow before exporting summaries.
metadata:
  owner: cloudpss-team
  category: export
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_model_parameter_extraction.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_revision_and_powerflow
---

# Model Parameter Extraction

## When to use

- 需要导出母线、线路、变压器、发电机、负荷或量测通道参数。
- 需要核对潮流输入设置，例如发电机 `pf_P`、`pf_V`、负荷 `p`、`q`。
- 需要把 CloudPSS 模型参数整理为 JSON/CSV 供外部分析使用。
- 需要在仿真前确认模型关键设备数量和参数字段是否完整。

## Workflow

1. 调用 `initModelAndCreateSACanvas(cloudpss_model=...)` 初始化真实模型。
2. 调用 `getRevision()`，从 `revision["implements"]["diagram"]["cells"]` 提取组件 `id`、`label`、`definition`、`args`、`pins`。
3. 使用共享包 getter 读取 `get_bus_all_keys`、`get_acline_all_keys`、`get_transformer_all_keys`、`get_generator_all_keys`、`get_load_all_keys`。
4. 调用 `get_power_flow_settings()`、`get_generator_all_p_set()`、`get_generator_all_v_set()`、`get_load_all_p_set()`、`get_load_all_q_set()` 读取潮流设置。
5. 运行 `power_flow_sample_simple_ramdom(..., P_low=1.0, P_high=1.0, V_low=1.0, V_high=1.0)` 验证参数能驱动真实潮流。
6. 调用 `get_bus_all_pf_result`、`get_acline_all_pf_result`、`get_generator_all_pf_result` 补充运行点结果。
7. 输出结构化参数摘要和样例记录。

## Output

- `component_counts`: 各类设备数量。
- `parameter_tables`: 母线、线路、变压器、发电机、负荷和通道样例参数。
- `power_flow_settings`: 潮流设置类型统计和样例。
- `power_flow_result_summary`: 真实潮流运行后的母线、支路和发电机结果摘要。

## Constraints

- 默认模型为 `model/yuanxuefeng/IEEE39`。
- 参数字段直接来自 CloudPSS revision，不做跨模型字段名标准化；下游使用前应保留原始 `definition`。
- 导出脚本默认只打印摘要和样例，避免把大型 revision 全量塞进 agent 上下文。
- 如果需要全量 CSV/JSON，可在验证脚本基础上打开 `CLOUDPSS_PARAM_EXPORT_FULL=1` 后写入本地 `results/skill-local-export/model-parameter-extraction`。

## Verified script

- `skills/model-parameter-extraction/scripts/verify_model_parameter_extraction.py`
