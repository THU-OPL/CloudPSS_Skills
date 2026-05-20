---
name: loss-analysis
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 对 CloudPSS 模型执行真实潮流仿真并分析支路有功/无功损耗、全网网损、损耗率、最高损耗支路和负荷扰动下的损耗敏感性。当用户需要网损分析、支路损耗排序、降损建议、损耗敏感性或潮流损耗报告时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: The verification script computes losses from real CloudPSS power-flow branch results.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_loss_analysis.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_powerflow_loss_analysis
---

# Loss Analysis

## When to use

- 需要计算全网有功网损、无功损耗和损耗率。
- 需要识别最高损耗支路、最高视在功率支路和可能的降损关注点。
- 需要比较负荷提升或下降后网损变化。
- 需要为运行方式调整、无功补偿或网架优化提供损耗证据。

## Workflow

1. 调用 `initModelAndCreateSACanvas(cloudpss_model=...)` 初始化真实模型。
2. 调用 `runProject(jobName="潮流计算方案 1", configName="参数方案 1")` 或确定性 `power_flow_sample_simple_ramdom` 执行潮流。
3. 使用 `get_acline_all_pf_result()` 读取支路首末端 P/Q。
4. 计算每条支路：
   - 有功损耗：`P_from + P_to`
   - 无功损耗：`Q_from + Q_to`
   - 两端最大视在功率：`max(sqrt(P_from^2+Q_from^2), sqrt(P_to^2+Q_to^2))`
5. 使用 `get_generator_all_pf_result()` 和负荷设定值计算全网损耗率。
6. 对负荷 `0.9/1.0/1.1` 缩放场景重复潮流，计算网损敏感性。
7. 输出损耗排序、全网指标、敏感性和工程建议。

## Output

- `base_case`: 基准潮流网损指标。
- `top_loss_branches`: 有功损耗最高的支路列表。
- `top_stress_branches`: 视在功率最高的支路列表。
- `load_sensitivity`: 负荷缩放对总网损的影响。
- `recommendations`: 基于损耗集中度和敏感性的简要建议。

## Constraints

- 默认模型为 `model/CloudPSS/IEEE39`。
- 支路损耗从潮流结果首末端功率相加得到，依赖 CloudPSS 支路表符号约定。
- 该 skill 不执行 OPF；“降损建议”只基于损耗排序和敏感性，不替代优化计算。
- 负荷敏感性会受到平衡机和发电机设定方式影响；若出现负荷增加但网损下降，应结合调度分配和无功电压控制解释。
- 若模型支路结果缺少额定容量，则只输出损耗和视在功率排序，不输出热稳百分比。

## Verified script

- `skills/loss-analysis/scripts/verify_loss_analysis.py`

