---
name: vsi-weak-bus-analysis
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 对 CloudPSS 模型执行动态无功注入式 VSI 分析，验证 addVSIQSource、addVSIMeasure 与 calculateVSI 的真实仿真闭环。当用户提到 VSI、弱母线识别、动态无功注入、薄弱母线排序或电压敏感度分析时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Uses the versioned cloudpss-psa-core shared package; do not import the old psa repository directly.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_vsi_weak_bus.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# VSI Weak Bus Analysis

## 何时使用

- 需要识别给定母线集合中的薄弱母线。
- 需要运行动态无功注入测试并生成 VSI 排名。
- 需要导出 VSI 结果 JSON 与本地图形。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`。
- 当前验证模型为 `model/yuanxuefeng/IEEE39`。
- 运行时依赖 `cloudpss-psa-core` 提供的 `psa.tool_box.PowerSystemAnalysis`。

## 已验证工作流

1. `initModelAndCreateSACanvas`
2. `power_flow_sample_simple_ramdom`
3. 选择真实母线子集
4. `addVSIQSource`
5. `addVSIMeasure`
6. `runProject`
7. `calculateVSI`

## 结果要点

- `calculateVSI` 返回 `VSIresultDict`、结果 JSON 路径与本地图形路径。
- 当前验证用真实模型中发现的 4 个母线做最小闭环验证，以控制仿真时长。

## 约束

- 当前 skill 的已验证闭环是“弱母线识别”，不包含后续补偿设计。
- 本地导出依赖 `SAVETOLOCAL=true`、`SAVETOMINIO=false`。

## 已验证脚本

- Python 直调：`skills/vsi-weak-bus-analysis/scripts/verify_vsi_weak_bus.py`
