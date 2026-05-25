---
name: transient-stability-margin
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行多次真实 EMT 仿真，通过修改本地工作副本中已有故障元件的切除时间，基于转速/频率波形和可选电压恢复判据估计临界切除时间 CCT、稳定裕度、稳定/失稳边界和扫描报告。当用户需要暂态稳定裕度、CCT、故障切除时间极限、稳定边界搜索或保护切除时间裕度评估时使用。该 skill 只依赖公开 cloudpss 包和本 skill 的 bundled runtime，不依赖其他 skill 或共享包。
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
  entrypoint: scripts/verify_transient_stability_margin.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_transient_stability_margin
---

# Transient Stability Margin

## Standards and references basis

- IEEE/CIGRE power system stability definition and classification: use transient stability and rotor-angle/speed response as the primary conceptual basis.
- Kundur, *Power System Stability and Control*: use time-domain disturbance simulation and critical clearing time search as the engineering method.
- NERC `TPL-001-5.1`: use planning-event stability screening and documented simulation evidence as the reliability-study context.
- NERC EMT Modeling Guideline for BPS-connected IBR: use real EMT simulation and explicit model/output-channel evidence for dynamic studies.
- ANDES/OpenDSS references: use independent time-domain simulation, fault-duration sweep, and waveform-based classification patterns as implementation references.

This skill is a CloudPSS EMT simulation screening tool. It does not claim formal NERC/IEEE/IEC compliance certification.

## When to use

- 需要估计故障切除时间上限、CCT 或 CCT 下界。
- 需要比较实际/基准切除时间与 CCT 的裕度。
- 需要对已有 EMT 故障场景做粗扫和二分搜索。
- 需要保留每个扫描点的真实 CloudPSS job id 和波形判据证据。
- 需要轻量、独立的 CCT skill，而不是调用其他故障扫描或暂稳报告 skill。

## Input contract

接受用户直接提供的等价 JSON 配置。模型中应已有 `_newFaultResistor_3p` 故障元件和必要输出通道；该 skill 不自动创建新故障元件。

- `scenario`
  - `fault_start`: 故障开始时间，默认读取故障元件 `fs`，否则默认 `2.5`。
  - `fault_resistance`: 故障电阻/深度参数 `chg`，默认读取故障元件，或默认 `0.01`。
  - `fault_component`: 可选故障元件 id/label/name；未指定时使用第一个 `_newFaultResistor_3p`。
- `search`
  - `coarse_clearing_times`: 粗扫故障持续时间列表，单位秒，例如 `[0.15, 0.25, 0.4]`。
  - `bisection_tolerance`: 找到稳定/失稳包络后使用二分搜索的时间精度，默认 `0.01` 秒。
  - `max_bisection_iterations`: 二分最大次数，默认 `8`。
  - `baseline_clearing_time`: 用于计算裕度的基准故障持续时间，默认取粗扫最小值。
  - `timeout`: 单个 EMT job 超时时间，默认 `300` 秒。
- `assessment`
  - `base_frequency_hz`: 基准频率，默认 `50.0` Hz。
  - `analysis_window`: 波形分析窗口，默认全时段。
  - `prefault_window`: 初值窗口，默认故障前短窗口。
  - `postfault_window`: 稳态窗口，默认仿真末段短窗口。
  - `speed_channels`: 标幺转速通道，例如 `#wr1:0`、`#wr2:0`、`#wr3:0`。
  - `frequency_channels`: Hz 频率通道，内部会换算为 pu。
  - `voltage_pu_channels`: 可选 pu/RMS 电压恢复判据通道。
  - `support_channels`: 可选支撑波形通道，只记录指标，不参与稳定布尔结论。
  - `max_speed_deviation_pu`: 最大转速偏差阈值，默认 `0.02` pu。
  - `final_speed_deviation_pu`: 末段稳态偏差阈值，默认 `0.005` pu。
  - `settling_threshold_pu`: 稳定时间阈值，默认 `0.003` pu。
  - `max_rocof_hz_per_s`: RoCoF 阈值，默认 `10.0` Hz/s。
  - `voltage_recovery_limit_pu`: 可选电压恢复阈值，默认 `0.9` pu。
  - `min_samples`: 单通道最小样本数，默认 `128`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 拒绝公开占位 RID 作为 live verification 来源。
3. 找到已有故障元件和目标输出通道。
4. 对每个粗扫切除时间克隆本地工作副本，设置 `fs`、`fe=fs+clearing_time`、`chg`。
5. 调用真实 CloudPSS `runEMT()` 并提取转速/频率/可选电压波形。
6. 对每个扫描点判断稳定性：转速偏差、末段偏差、稳定时间、RoCoF 和可选电压恢复。
7. 若粗扫找到稳定/失稳包络，则在包络内二分搜索 CCT；否则输出 `CCT >= 最大稳定切除时间` 或 `CCT <= 最小失稳切除时间`。
8. 计算基准切除时间相对 CCT/下界的裕度。
9. 导出 JSON、CSV 和 Markdown 报告。

## Output

- 每个扫描点的故障持续时间、故障结束时间、CloudPSS job id、稳定性和判据证据。
- `summary.cct_seconds`、`summary.cct_relation`、`summary.search_status`。
- `summary.margin_seconds`、`summary.margin_percent`、`summary.baseline_clearing_time`。
- `summary.stable_points`、`summary.unstable_points` 和最薄弱通道。
- JSON、CSV 和 Markdown 产物路径。

## Constraints

- 该 skill 只修改本地工作副本，不保存云端模型修改。
- 当前只支持模型中已有 `_newFaultResistor_3p` 的故障持续时间搜索，不自动创建新故障或断路器逻辑。
- CCT 判据是基于配置通道的波形初筛；正式工程结论应结合功角、保护动作、故障类型、关键母线电压和模型审查。
- 如果搜索区间内没有稳定/失稳交界，结果会以 `>=` 或 `<=` 形式给出边界，不伪造精确 CCT。
- 多次 EMT 仿真耗时较高，建议先用 3-5 个粗扫点验证趋势，再缩小搜索区间。

## Live verification

- 验证日期：`2026-05-25`
- 验证模型：`model/CloudPSS/IEEE3`
- 故障元件 key：`canvas_0_1150`
- 故障开始时间：`2.5 s`
- 故障电阻参数：`0.01`
- 粗扫故障持续时间：`[0.15, 0.25, 0.4] s`
- 基准切除时间：`0.15 s`
- 监测转速通道：`#wr1:0`、`#wr2:0`、`#wr3:0`
- 支撑波形通道：`vac:0`、`vac:1`、`vac:2`
- EMT job ids:
  - `0.15 s`: `f9abe55c-4aa2-4b3d-9383-b60046a2975d`
  - `0.25 s`: `e0eadead-be8b-4c22-8670-1482cfb2e715`
  - `0.40 s`: `8261ea2e-83b0-4dcc-9bd3-1e391d0209ad`
- 验证摘要：3 个真实 EMT 扫描点全部稳定；配置搜索上界内未找到失稳点，因此输出 `CCT >= 0.4 s`。相对 `0.15 s` 基准切除时间的裕度下界为 `0.25 s`，约 `62.5%`。
- 最大转速偏差约 `0.010792 pu`，最大 RoCoF 约 `4.655645 Hz/s`，最薄弱通道为 `#wr1:0`。
- 验证产物：
  - `results/skill-verification/transient-stability-margin/transient_stability_margin_20260525_164948.json`
  - `results/skill-verification/transient-stability-margin/transient_stability_margin_20260525_164948.csv`
  - `results/skill-verification/transient-stability-margin/transient_stability_margin_report_20260525_164948.md`

## Verified script

- `skills/transient-stability-margin/scripts/verify_transient_stability_margin.py`
