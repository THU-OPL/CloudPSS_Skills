---
name: fault-clearing-scan
description: 使用 CloudPSS SDK 扫描不同故障切除时间对恢复电压的影响，并输出趋势排序、JSON、CSV 和 Markdown 报告。当用户需要故障切除时间扫描、恢复裕度排序或临界切除时间早期筛查时使用。可消费 fault-scenario-editor 蓝图或等价 JSON 配置，但不依赖其他 skill 的代码。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Accepts the fault-clearing input contract documented in this SKILL.md or an equivalent JSON config. Runtime stays self-contained and does not import sibling skills.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: experimental
  entrypoint: scripts/verify_fault_clearing_scan.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_fault_clearing_scan
---

# Fault Clearing Scan

## When to use

- 需要扫描不同故障切除时间 `fe` 对恢复电压的影响。
- 需要对同一故障蓝图下的多个 `fe_values` 做排序比较。
- 需要从 `fault-scenario-editor` 输出的模板继续做 EMT 故障切除扫描。
- 需要一个独立的故障扫描 skill，而不是依赖其他 skill 的 runtime。

## Input contract

接受 `fault-scenario-editor` 生成的 `fault_clearing_scan` 模板，也接受用户直接提供的等价 JSON 配置。`fault-scenario-editor` 是推荐的场景准备工具，不是硬前置依赖。

输入字段：

- `fault_point`
  - `fault_bus`: 故障母线或锚点，可为空但应记录。
  - `fault_type`: 默认 `three_phase`。
  - `fault_time`: 故障开始时间，对应 `scan.fs`。
  - `fault_duration`: 可由每个 `fe - fs` 推导。
  - `fault_resistance`: 对应 `scan.chg`。
- `breaker_action`
  - `mode`: 建议 `trip_after_scan`。
  - `clearing_policy`: 建议 `vary_fe`。
- `scan`
  - `fs`: 故障开始时间。
  - `fe_values`: 要扫描的故障切除时间列表。
  - `chg`: 固定故障电阻。
- `assessment`
  - `trace_name`: 目标波形通道，例如 `vac:0`。
  - `study_time`: 恢复评估时刻。
  - `sampling_freq`: 可选，默认 `2000`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

如果没有外部配置，runtime 使用本 skill 的默认 `fs / fe_values / chg / trace_name / study_time` 执行扫描。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 读取蓝图模板中的 `scan.fs`、`scan.fe_values`、`scan.chg` 和 `assessment.trace_name`、`assessment.study_time`。
3. 对每个 `fe` 构造本地工作副本并更新故障参数。
4. 运行真实 CloudPSS EMT 仿真。
5. 在研究时刻提取目标通道电压值。
6. 生成 JSON、CSV 和 Markdown 输出。
7. 按 `fe` 升序整理结果并判断是否单调恶化。

## Output

- 每个 `fe` 对应的 job id 和研究时刻电压。
- `monotonic_degradation` 趋势判断。
- JSON、CSV 和 Markdown 产物路径。
- 可复核的结构化摘要。

## Constraints

- skill 不依赖 `fault-scenario-editor` 的代码；只需要等价输入配置。
- 默认验证模型使用 `CLOUDPSS_TEST_EMT_MODEL_RID`，公开使用时请传入自己账号下的 EMT-ready 模型 RID。
- `model/holdme/*` 不作为 live verification 来源。
- 如果模型没有故障元件或量测通道，验证会失败。

## Verified script

- `skills/fault-clearing-scan/scripts/verify_fault_clearing_scan.py`
