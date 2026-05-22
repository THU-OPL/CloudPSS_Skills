---
name: parameter-sensitivity-analysis
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行单参数小规模灵敏度扫描，修改本地工作副本中的指定组件参数，运行多次真实 EMT 仿真，提取目标通道指标，并计算线性灵敏度、归一化灵敏度和排序报告。当用户需要参数扫描、参数灵敏度、负荷/线路/控制参数变化对 EMT 波形指标的影响、敏感指标排序或参数调优初筛时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Set CLOUDPSS_TEST_EMT_MODEL_RID or pass an EMT-ready model RID. Verification uses model/CloudPSS/IEEE3 and refuses placeholder or model/holdme/* sources.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_parameter_sensitivity_analysis.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_parameter_sensitivity_analysis
---

# Parameter Sensitivity Analysis

## When to use

- 需要对一个明确模型参数做小规模扫描并运行真实 CloudPSS EMT。
- 需要量化参数变化对转速、功率、电压等波形指标的影响。
- 需要输出 `dy/dx` 线性灵敏度、归一化灵敏度和敏感指标排序。
- 需要轻量、独立的参数扫描 skill，而不是共享 PSA 包或跨 skill 编排。

## Input contract

接受用户直接提供的等价 JSON 配置。参数目标必须显式指定组件和参数名，避免自动猜测导致误改模型。

- `scan`
  - `target`: 目标参数。可用对象形式 `{"component": "newExpLoad-2", "arg": "p"}`，也可用字符串形式 `"newExpLoad-2.p"`。
  - `values`: 参数扫描值列表，至少 2 个值；建议 3-5 个点。
  - `reference`: 参考值，用于归一化灵敏度；默认取扫描值中间点。
  - `simulation_type`: 当前独立 runtime 只支持 `emt`。
  - `timeout`: 单个 EMT job 超时时间，默认 `300` 秒。
- `metrics`
  - `channels`: 明确要提取的通道列表，例如 `#P1:0`、`#wr1:0`、`vac:0`。
  - `auto_max_channels`: 未指定通道时自动选择的最大通道数，默认 `6`。
  - `metric_names`: 每个通道提取的指标，默认 `mean`、`rms`、`min`、`max`、`peak_to_peak`、`final`。
  - `time_window`: 指标计算时间窗 `[start, end]`；默认使用全仿真时间。
  - `min_samples`: 单通道最小样本数，默认 `128`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝 `model/holdme/*` 和公开占位 RID 作为 live verification 来源。
3. 在基础模型中按组件 id、label、name 或 `Name` arg 解析目标组件。
4. 对每个扫描值创建本地工作副本，调用 `updateComponent` 修改目标参数。
5. 对每个工作副本调用真实 CloudPSS `runEMT()` 并轮询到完成。
6. 从每个 job result 中读取目标通道并计算指标。
7. 对每个指标做线性回归，计算 `sensitivity = dy/dx`。
8. 计算 `normalized_sensitivity = dy/dx * reference / mean(metric)`。
9. 导出 JSON、灵敏度 CSV、扫描点 CSV 和 Markdown 报告。

## Output

- 每个扫描点的参数值、CloudPSS job id 和通道指标。
- `sensitivity_ranking`：按归一化灵敏度绝对值排序的指标列表。
- `summary.successful_points`、`summary.failed_points`、`summary.metric_count`、`summary.top_metric`。
- JSON、CSV、扫描点 CSV 和 Markdown 产物路径。

## Live verification

- 验证日期：`2026-05-22`
- 验证模型：`model/CloudPSS/IEEE3`
- 扫描参数：`newExpLoad-2.p`
- 组件 key：`canvas_0_1084`
- 扫描值：`[90.0, 100.0, 110.0]`
- 参考值：`100.0`
- EMT job ids:
  - `90.0`: `49018bb2-3445-448b-a2db-5af3a7a562f1`
  - `100.0`: `edf722d3-935b-41fe-bbfa-56355b9a7cc0`
  - `110.0`: `f2b28bd3-90c8-4db1-8b6f-4ff35558cf43`
- 验证摘要：3 个扫描点成功、0 个失败、18 个指标；最敏感指标为 `#P3:0.final`，归一化灵敏度约 `0.40628938538804643`。
- 验证产物：
  - `results/skill-verification/parameter-sensitivity-analysis/parameter_sensitivity_analysis_20260522_143602.json`
  - `results/skill-verification/parameter-sensitivity-analysis/parameter_sensitivity_analysis_20260522_143602.csv`
  - `results/skill-verification/parameter-sensitivity-analysis/parameter_sensitivity_analysis_scan_points_20260522_143602.csv`
  - `results/skill-verification/parameter-sensitivity-analysis/parameter_sensitivity_analysis_report_20260522_143602.md`

## Constraints

- 该 skill 只修改本地工作副本，不保存云端模型修改。
- 当前只支持 `simulation_type="emt"`，不实现潮流模式，避免引入共享 PSA 运行时。
- 只建议做单参数、小规模扫描；多参数正交试验应另建 `orthogonal-sensitivity-analysis`。
- 灵敏度为扫描区间内的线性近似，非线性强或扫描点失败时不能作为正式工程结论。
- 如果目标组件/参数不存在、通道不存在、样本数不足或 EMT 仿真失败，验证脚本直接失败。

## Verified script

- `skills/parameter-sensitivity-analysis/scripts/verify_parameter_sensitivity_analysis.py`
