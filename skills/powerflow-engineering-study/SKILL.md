---
name: powerflow-engineering-study
description: 使用 CloudPSS SDK 在本地研究副本上执行潮流工程分析，包括线路切除、电压设定值调整、有功重调度、负荷转移和无功压力场景。当用户提到工程化潮流比较、线路停运影响、电压控制或负荷转移研究时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: false
  required_env_vars: []
  notes: Requires a valid .cloudpss_token file in the working directory.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_powerflow_engineering_study.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_sdk
---

# Powerflow Engineering Study

## When to use

- 需要做工程化潮流场景比较
- 需要比较线路切除前后结果
- 需要做发电机电压或有功重调度分析
- 需要做负荷转移或无功压力研究

## Workflow

1. 读取 `.cloudpss_token`
2. 获取或加载 IEEE39 模型
3. 执行基准潮流
4. 在本地工作副本上修改组件参数
5. 执行调整后潮流
6. 输出结构化比较结果

## Output

- 基准与调整场景摘要
- 关键母线与线路变化
- 研究结论所需的对比结果

## Constraints

- 示例当前固定使用已验证的 IEEE39 目标对象
- 主要体现“独立 skill + 本地副本 + 工程比较”模式
- 不依赖 MCP
