---
name: reactive-compensation-design
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis，基于 VSI 结果与真实扰动场景执行无功补偿设计，验证 batchAddSyncComp 与 iterativeSolutionQ 的真实仿真闭环。当用户提到无功补偿设计、调相机容量迭代、基于 VSI 的补偿布置或扰动后电压恢复补偿时使用。
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
  entrypoint: scripts/verify_reactive_compensation_design.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# Reactive Compensation Design

## 何时使用

- 需要根据 VSI 结果为目标母线布置调相机。
- 需要在真实扰动场景下迭代调节无功补偿容量。
- 需要验证 `iterativeSolutionQ` 是否能返回迭代任务和容量调整结果。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`。
- 当前验证模型为 `model/CloudPSS/IEEE39`。
- 运行时依赖 `cloudpss-psa-core` 提供的 `psa.tool_box.PowerSystemAnalysis`。
- 为控制验证时长，验证脚本默认设置 `SSC_MAX_ITERATION_COUNT=4`。

## 已验证工作流

1. 先执行一轮 `calculateVSI` 生成本地 VSI 结果文件
2. 重新初始化模型
3. `power_flow_sample_simple_ramdom`
4. `runProject` 获取潮流结果 ID
5. `batchAddSyncComp`
6. `generate_random_fault_params_set_N_1`
7. `addVoltageMeasures`
8. `iterativeSolutionQ`

## 结果要点

- 当前验证使用真实模型里发现的 4 个母线做最小补偿设计闭环。
- `iterativeSolutionQ` 当前已支持直接读取本地 VSI 结果文件路径。

## 约束

- 当前 skill 的已验证设备类型为同步调相机链路，不覆盖 PCS/SVC 的组合优化。
- 本地导出依赖 `SAVETOLOCAL=true`、`SAVETOMINIO=false`。

## 已验证脚本

- Python 直调：`skills/reactive-compensation-design/scripts/verify_reactive_compensation_design.py`

