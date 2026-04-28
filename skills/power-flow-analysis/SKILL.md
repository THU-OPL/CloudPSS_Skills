---
name: power-flow-analysis
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis，对 CloudPSS 模型执行稳态潮流计算，读取母线、线路、发电机结果，并完成基准工况、负荷提升和发电机电压设定值调整等确定性分析。 当用户提到潮流计算、母线电压、线路潮流、负荷提升、发电机电压设定值、运行点对比时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Prefer running the local verify script with a checked-out .py file, not an inline python - command, when debugging real CloudPSS execution.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_power_flow.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# Power Flow Analysis

## When to use

- 需要对 CloudPSS 模型执行稳态潮流计算
- 需要读取母线电压、线路有功潮流、发电机出力
- 需要比较基准工况与负荷上调或发电机电压设定值调整后的差异

## Workflow

1. 读取 `.env` 中的 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`
2. 调用 `initModelAndCreateSACanvas(cloudpss_model="model/yuanxuefeng/IEEE39")`
3. 基准工况使用 `power_flow_sample_simple_ramdom(..., P_low=1.0, P_high=1.0, V_low=1.0, V_high=1.0)`
4. 读取 `get_bus_all_pf_result`、`get_acline_all_pf_result`、`get_generator_all_pf_result`
5. 若要做确定性场景修改，先用 `runProject(...)` 得到当前工况，再调用 `set_load_all_*` 或 `set_generator_all_v_set`
6. 手动改值后只能重新调用 `runProject(...)`，不要再调用 `power_flow_sample_simple_ramdom(...)` 覆盖场景
7. 输出基准与调整后场景的结构化对比结果

## Output

- 母线结果：`[bus_key, bus_label, voltage, angle, gen_P, gen_Q]`
- 线路结果：`[line_key, from_bus, to_bus, P_from, Q_from, P_to, Q_to]`
- 发电机结果：`[gen_keys, gen_v, gen_p, gen_q]`
- 对比摘要：母线电压统计、线路有功损耗、总发电有功/无功、负荷调整或电压设定值调整前后差异

## Constraints

- 当前示例固定使用 `model/yuanxuefeng/IEEE39`
- 不依赖 MCP，直接使用 Python + CloudPSS SDK
- 共享 PSA 逻辑来自 `cloudpss-psa-core`，不要再从旧 `psa/` 仓库目录直接 import
- 批量 `set_*` 的输入顺序必须与对应 getter 返回顺序一致
- 调试真实 CloudPSS 执行时，优先运行仓库内 `.py` 脚本，不使用内联 `python -`
