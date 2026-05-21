---
name: result-compare-and-visualization
description: 使用 CloudPSS SDK 对两次或多次真实 EMT 仿真结果提取同名波形通道，计算最大值、最小值、均值、RMS、峰峰值等指标差异，并生成 Markdown/JSON 摘要和 PNG 对比图。当用户需要多场景暂态波形对比、仿真结果可视化、指标差异排序或报告图表产物时使用。
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
  entrypoint: scripts/verify_result_compare_and_visualization.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_result_compare_visualization
---

# Result Compare And Visualization

## When to use

- 需要比较多个 CloudPSS EMT 仿真工况的波形差异。
- 需要提取同名通道的 max、min、mean、rms、peak-to-peak 等指标。
- 需要生成用于报告的 Markdown/JSON 摘要和 PNG 图表。
- 需要对故障参数、切除时间或运行方式调整前后的结果做快速排序。

## Workflow

1. 加载 token 和 EMT-ready 模型；公开使用时通过 `CLOUDPSS_TEST_EMT_MODEL_RID` 或命令行传入自己账号下的模型 RID。
3. 运行至少两个真实 CloudPSS EMT 场景。
4. 从每个 `job.result` 中读取目标 plot/channel 的 `x/y` 波形。
5. 对同名通道计算指标，并计算相对基准的差异。
6. 生成 JSON、Markdown 和 PNG 对比图。
7. 校验所有产物存在且差异指标不为空。

## Output

- 每个场景的 job id、标签和通道统计。
- 同名通道指标对比表。
- 差异排序摘要。
- PNG 波形叠加图和指标柱状图。
- Markdown/JSON 报告文件。

## Constraints

- 默认验证使用同一模型的两个本地工作副本，不保存远端模型修改。
- 如果模型没有可调整的故障元件，则退化为两次基准 EMT 仿真，但仍要求真实 CloudPSS job 和通道数据可读。
- 图表使用 matplotlib Agg 后端生成，适合无 GUI 环境。
- 如果账号下没有 IEEE3 EMT 样例，先从官方 `model/CloudPSS/IEEE3` 保存或构建到自己账号，再传入该新 RID；本仓库实测使用的是私有 EMT-ready 副本，不作为公开默认值。

## Verified script

- `skills/result-compare-and-visualization/scripts/verify_result_compare_and_visualization.py`
