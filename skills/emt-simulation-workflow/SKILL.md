---
name: emt-simulation-workflow
description: 使用 CloudPSS SDK 对 EMT-ready 模型执行完整 EMT 仿真 workflow，包括加载云端或本地模型、检查 EMT topology、提交 `runEMT()` 任务、轮询任务状态、提取 plot 与 channel 摘要，并按需导出 CSV 波形文件。当用户提到 EMT 仿真、暂态时域波形、EMT topology 检查、输出通道巡检、仿真任务状态确认或波形导出时使用。该 skill 适合作为贡献者提交示例，因为它只依赖公开 Python 包 `cloudpss` 和 skill 目录内的最小 `mylib/` 代码，不依赖仓库外私有源码目录。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Prefer running the checked-in verify script instead of inline `python -` when validating real CloudPSS execution. The runtime first reads `.cloudpss_token`; if that file is absent, it falls back to `.env` for `SIMSTUDIO_TOKEN` and `CLOUDPSS_API_URL`.
metadata:
  owner: cloudpss-team
  category: workflow
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_emt_simulation_workflow.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_sdk
---

# Emt Simulation Workflow

## When to use

- 需要对一个 EMT-ready CloudPSS 模型执行一次完整 EMT 仿真
- 需要确认模型是否具备可用的 EMT topology 和 `runEMT()` 执行能力
- 需要读取 plot 分组、channel 名称和基础波形结果摘要
- 需要导出一组可复核的 CSV 结果给后续分析或评审使用
- 需要一个独立、最小依赖、适合贡献者模仿提交的新 skill 示例

## Submission pattern

这个 skill 用来演示一类最容易审查和合并的贡献方式：

- 第三方依赖只写在 `requirements.txt`
- 自定义逻辑只放在当前 skill 的 `mylib/`
- 验证入口固定为 `scripts/verify_emt_simulation_workflow.py`
- 不从 `psa/`、`CloudPSS_skillhub/` 或其他仓库外目录直接 import
- 不要求 MCP 服务

如果后续多个 skill 需要复用同一套较大的私有能力，应优先抽成独立共享包，再在 `requirements.txt` 中固定到 tag 或 commit；这个示例刻意不走共享包路径，用于展示“单 skill 自包含提交”的最小模式。

## Workflow

1. 优先读取当前工作目录下的 `.cloudpss_token`
2. 如果 `.cloudpss_token` 不存在，则回退读取上层工作区 `.env` 中的 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`
3. 使用 `Model.fetch()` 或 `Model.load()` 加载云端 RID 或本地模型文件
4. 调用 `fetchTopology(implementType="emtp")` 检查 EMT topology 是否可用
5. 调用 `model.runEMT()` 创建 EMT 仿真任务
6. 轮询 `job.status()`，直到成功、失败或超时
7. 读取 `job.result`，提取 plot 分组和 channel 摘要
8. 为每个 plot 导出首个 channel 的 CSV 文件，作为最小复核产物

## Output

- 模型来源、模型名称、模型 RID
- EMT topology 摘要
- EMT 仿真任务 ID 与最终状态
- plot 数量、plot 名称、channel 数量、channel 预览
- 导出的 CSV 文件路径列表

## Verified example

该 skill 已在真实 CloudPSS 环境完成过一次直接验证：

- date: 2026-04-28
- model: private EMT-ready IEEE3 copy under the verifier's own account
- model_name: `3机9节点标准测试系统`
- job_id: `1fefdadb-d7bf-4a93-917a-fccc2f850f58`
- final_status: `1`
- plot_count: `3`

公开使用时，默认模型 RID 已切换为 `model/<your-account>/IEEE3` 占位符。用户需要传入自己账号下的 EMT-ready 模型 RID，或先从官方 `model/CloudPSS/IEEE3` 保存/构建到自己的账号，再执行验证。

导出的示例产物位于：

- `results/skill-verification/emt-simulation-workflow/plot_0_#wr1_0.csv`
- `results/skill-verification/emt-simulation-workflow/plot_1_#P2_0.csv`
- `results/skill-verification/emt-simulation-workflow/plot_2_vac_0.csv`

## Maintainer review focus

维护者审查这类 skill 时，优先检查：

- `SKILL.md` 描述的能力是否与脚本真实行为一致
- `requirements.txt` 是否只包含必要依赖，且未依赖仓库外私有目录
- `mylib/` 是否是最小必需代码，而不是复制整仓旧代码
- `evals/evals.json` 是否描述了真实可复现的评估任务
- `scripts/verify_emt_simulation_workflow.py` 是否能在标准环境下直接运行
- 失败条件是否清楚，例如模型无权限、无 EMT topology、任务失败或超时

## Constraints

- 当前示例只覆盖标准 CloudPSS SDK EMT workflow，不覆盖 MCP 或实时控制接口
- skill 假定目标模型已具备可执行的 EMT topology 和仿真配置
- 默认只导出每个 plot 的首个 channel，避免贡献示例生成过大的测试产物
- 如果目标模型 RID 不存在或当前 token 无权限，验证脚本会直接失败
- 如果要扩展为更复杂的 EMT 研究流程，应先确认是否仍适合保留在单 skill 的 `mylib/` 中
