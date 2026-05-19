---
name: steady-state-contingency-analysis
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 对 CloudPSS 模型执行稳态 N-1 预想事故筛查，通过真实潮流仿真比较基准工况与线路退运场景，输出潮流收敛状态、电压越限、支路应力、损耗变化和严重度排序。当用户需要稳态 N-1、安全校核、预想事故筛查、电压越限或热稳风险排序时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: The verification script runs real CloudPSS power flow for base and contingency cases; thermal loading is reported only when rating data is available.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: experimental
  entrypoint: scripts/verify_steady_state_contingency_analysis.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_powerflow_contingency
---

# Steady State Contingency Analysis

## When to use

- 需要做稳态 N-1 或预想事故筛查。
- 需要比较线路退运后母线电压、支路应力、网损和潮流收敛状态。
- 需要输出最严重事故排序和需要重点关注的线路。
- 需要在暂态 N-1 前先做低成本稳态筛选。

## Workflow

1. 调用 `initModelAndCreateSACanvas(cloudpss_model=...)` 初始化真实模型。
2. 调用 `runProject(jobName="潮流计算方案 1", configName="参数方案 1")` 运行基准潮流。
3. 从 `get_acline_all_keys()` 和真实 revision 中选取候选线路。
4. 对每个候选线路新建模型实例，使用 `project.removeComponent(line_key)` 从本地工作副本删除该线路，运行真实潮流。
5. 若潮流不收敛，记录为最高严重度事故。
6. 若潮流收敛，读取 `get_bus_all_pf_result` 与 `get_acline_all_pf_result`，统计：
   - 电压低越限和高越限。
   - 支路两端最大 MVA 应力。
   - 有功损耗变化。
   - 若模型提供额定值，计算热稳百分比。
7. 计算严重度并排序输出。

## Output

- `base_case`: 基准潮流电压、支路和损耗摘要。
- `contingencies`: 每个线路退运场景的收敛状态、越限和指标。
- `severity_ranking`: 从严重到轻微的事故排序。
- `unsupported`: 无额定值或无法稳定退运的限制说明。

## Constraints

- 当前验证默认只筛查前若干条真实线路，数量由 `CLOUDPSS_CONTINGENCY_LIMIT` 控制，默认 3。
- 线路退运通过 `project.removeComponent(line_key)` 在本地工作副本删除线路实现；不同模型的 CloudPSS 组件可能需要更专门的停运字段。
- 热稳校核只有在支路组件包含 `Irated` 和 `Vbase` 或变压器 `Tmva` 等额定值时才输出百分比；否则输出支路 MVA 应力排序。
- maturity 标为 `experimental`，因为稳态退运语义仍依赖模型组件字段，需要更多算例验证后再提升为 validated。

## Verified script

- `skills/steady-state-contingency-analysis/scripts/verify_steady_state_contingency_analysis.py`
