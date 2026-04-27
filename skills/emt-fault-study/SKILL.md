---
name: emt-fault-study
description: 使用 CloudPSS SDK 对准备好的 EMT 模型执行故障研究，并比较故障切除时间和故障严重程度变化对波形恢复的影响。当用户提到 EMT 故障研究、故障切除时间比较或故障后恢复分析时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: false
  required_env_vars: []
  notes: Requires a valid .cloudpss_token file in the working directory and an EMT-ready model.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_emt_fault_study.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_sdk
---

# Emt Fault Study

## When to use

- 需要做 EMT 故障研究
- 需要比较不同故障清除时间
- 需要比较故障严重程度对恢复的影响

## Workflow

1. 读取 `.cloudpss_token`
2. 获取或加载 IEEE3 EMT 模型
3. 准备多个故障场景
4. 执行 EMT 仿真
5. 提取目标波形
6. 计算故障与恢复窗口指标

## Output

- 各工况的电压恢复指标
- 相对于基线工况的比较结果
- 结论所需的结构化摘要

## Constraints

- 当前示例依赖已准备好的 IEEE3 EMT 模型
- 结论只对当前固定通道和时间窗口成立
- 不依赖 MCP
