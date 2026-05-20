---
name: batch-powerflow-study
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 对 CloudPSS 模型执行多工况稳态潮流批量研究，比较基准工况、负荷缩放、发电机电压设定值调整和随机潮流样本对母线电压、线路损耗、发电出力的影响。当用户需要批量潮流、多运行方式对比、负荷增长影响、运行点扫描或潮流场景排序时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: The live verification runs several real CloudPSS power-flow jobs on a fresh model instance for each scenario.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_batch_powerflow_study.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_batch_powerflow
---

# Batch Powerflow Study

## When to use

- 需要对同一模型批量计算多个稳态潮流工况。
- 需要比较负荷提升、负荷下降、发电机电压设定值调整后的电压和网损变化。
- 需要获得多场景运行点的排序，例如最低电压、最高电压、支路有功损耗。
- 需要为稳态安全校核、网损分析或报告生成提供批量潮流输入。

## Workflow

1. 为每个场景新建一个 `PowerSystemAnalysis` 实例，避免上一场景的参数残留影响下一场景。
2. 调用 `initModelAndCreateSACanvas(cloudpss_model=...)` 初始化模型。
3. 对基准和随机样本，调用 `power_flow_sample_simple_ramdom` 运行真实潮流。
4. 对确定性负荷或电压设定场景，先读取 `get_load_all_*` 或 `get_generator_all_v_set`，修改后调用 `runProject`。
5. 每次运行后读取 `get_bus_all_pf_result`、`get_acline_all_pf_result`、`get_generator_all_pf_result`。
6. 汇总每个场景的母线电压统计、线路损耗、总发电出力和越限数量。
7. 输出按最低电压和总有功损耗排序的场景列表。

## Output

- `scenarios`: 每个潮流场景的设置、runner id 和指标。
- `rankings`: 按最低电压、最高电压、线路有功损耗排序。
- `comparison`: 与基准工况相比的电压、损耗、发电出力差值。

## Constraints

- 默认模型为 `model/CloudPSS/IEEE39`。
- 批量脚本使用串行运行，优先保证可追踪性；若要并发运行，应改用 `SimulationOrchestrator` 并限制 CPU。
- 批量 `set_load_all_*` 与 `set_generator_all_v_set` 的输入顺序必须与共享包 getter 返回顺序一致。
- 调整后场景使用 `runProject`，不要再调用 `power_flow_sample_simple_ramdom` 覆盖手工设定。

## Verified script

- `skills/batch-powerflow-study/scripts/verify_batch_powerflow_study.py`

