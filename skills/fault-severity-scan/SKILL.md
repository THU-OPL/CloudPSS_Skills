---
name: fault-severity-scan
description: 使用 CloudPSS SDK 扫描不同故障电阻对电压跌落和恢复缺口的影响，并输出严重度排序、JSON、CSV 和 Markdown 报告。当用户需要故障严重度扫描、故障电阻扫描、电压跌落评估或恢复能力对比时使用。可消费 fault-scenario-editor 蓝图或等价 JSON 配置，但不依赖其他 skill 的代码。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Accepts the fault-severity input contract documented in this SKILL.md or an equivalent JSON config. Runtime stays self-contained and does not import sibling skills.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: experimental
  entrypoint: scripts/verify_fault_severity_scan.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_fault_severity_scan
---

# Fault Severity Scan

## When to use

- 需要扫描不同故障电阻 `chg` 对故障中电压跌落的影响。
- 需要比较故障前、故障中、故障后三个时间窗的 RMS。
- 需要从 `fault-scenario-editor` 输出的模板继续做 EMT 故障严重度扫描。
- 需要一个独立的故障扫描 skill，而不是依赖其他 skill 的 runtime。

## Input contract

接受 `fault-scenario-editor` 生成的 `fault_severity_scan` 模板，也接受用户直接提供的等价 JSON 配置。`fault-scenario-editor` 是推荐的场景准备工具，不是硬前置依赖。

输入字段：

- `fault_point`
  - `fault_bus`: 故障母线或锚点，可为空但应记录。
  - `fault_type`: 默认 `three_phase`。
  - `fault_time`: 故障开始时间，对应 `scan.fs`。
  - `fault_duration`: 可由 `scan.fe - scan.fs` 推导。
  - `fault_resistance`: 可记录默认值；扫描时以 `scan.chg_values` 为准。
- `breaker_action`
  - `mode`: 建议 `keep_clear_time_fixed`。
  - `clear_time`: 固定切除时间，对应 `scan.fe`。
- `scan`
  - `fs`: 故障开始时间。
  - `fe`: 固定故障切除时间。
  - `chg_values`: 要扫描的故障电阻列表。
- `assessment`
  - `trace_name`: 目标波形通道，例如 `vac:0`。
  - `time_windows.prefault`: 故障前 RMS 时间窗 `[start, end]`。
  - `time_windows.fault`: 故障中 RMS 时间窗 `[start, end]`。
  - `time_windows.postfault`: 故障后 RMS 时间窗 `[start, end]`。
  - `sampling_freq`: 可选，默认 `2000`。
- `output`
  - `path`: 可选输出目录。
  - `prefix`: 可选文件名前缀。
  - `generate_report`: 是否生成 Markdown 报告。

如果没有外部配置，runtime 使用本 skill 的默认 `fs / fe / chg_values / trace_name / time_windows` 执行扫描。

## Workflow

1. 读取 token 并加载 EMT-ready 模型。
2. 读取蓝图模板中的 `scan.fs`、`scan.fe`、`scan.chg_values` 和 `assessment.trace_name`、`assessment.time_windows`。
3. 对每个 `chg` 构造本地工作副本并更新故障参数。
4. 运行真实 CloudPSS EMT 仿真。
5. 计算目标通道在故障前、故障中、故障后三个窗口的 RMS。
6. 计算 `fault_drop` 和 `postfault_gap`。
7. 生成 JSON、CSV 和 Markdown 输出，并判断趋势。

## Output

- 每个 `chg` 对应的 job id、三段 RMS、故障跌落和恢复缺口。
- `fault_trend` 和 `gap_trend` 趋势判断。
- JSON、CSV 和 Markdown 产物路径。
- 可复核的结构化摘要。

## Constraints

- skill 不依赖 `fault-scenario-editor` 的代码；只需要等价输入配置。
- 默认验证模型使用 `CLOUDPSS_TEST_EMT_MODEL_RID`，公开使用时请传入自己账号下的 EMT-ready 模型 RID。
- `model/holdme/*` 不作为 live verification 来源。
- 如果模型没有故障元件或量测通道，验证会失败。

## Verified script

- `skills/fault-severity-scan/scripts/verify_fault_severity_scan.py`
