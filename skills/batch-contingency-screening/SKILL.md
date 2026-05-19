---
name: batch-contingency-screening
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 SimulationOrchestrator 批量提交 CloudPSS 暂态仿真任务，执行随机 N-1 故障筛查、轮询后台任务状态，并回收批量结果摘要。当用户提到批量故障筛查、批量 N-1 扫描、异步仿真队列、批量任务状态查询或批量结果回收时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Requires the batch extra of cloudpss-psa-core because SimulationOrchestrator imports Ray.
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_batch_contingency_screening.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# Batch Contingency Screening

## 何时使用

- 需要把单次 N-1 暂态校核扩展成后台批量任务。
- 需要提交异步批量仿真，再轮询任务状态并获取摘要结果。
- 需要同时拿到每个工况的暂态检查结果和故障信息摘要。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`。
- 当前验证模型为 `model/yuanxuefeng/IEEE39`。
- 运行时依赖 `cloudpss-psa-core[batch]` 提供的 `psa.tool_box.SimulationOrchestrator`。
- 批量任务建议显式设置：
  `PSA_TASKS_DIR`
  `PSA_LOCAL_SAVE_DIR`
  `RAY_NUM_CPUS`
  `SAVETOLOCAL=true`
  `SAVETOMINIO=false`

## 已验证工作流

1. 可先调用 `get_step_temp()` 查看当前 repo 提供的标准模板说明。
2. 用显式 `flow.steps` 调用 `submit_batch_simulation(...)`。
3. 周期性调用 `query_batch_simulation_status(task_id)`，直到状态为 `completed` 或 `failed`。
4. 调用 `get_batch_simulation_result(task_id)` 获取结果摘要与 `result_file`。
5. 必要时调用 `list_batch_simulation_tasks()` 查看历史任务，调用 `clear_batch_simulation_tasks()` 清空旧任务。

当前已验证的批量 `flow.steps` 基于 `src/psa` 真实可运行链路：

1. `initModelAndCreateSACanvas`
2. `power_flow_sample_simple_ramdom`
3. `generate_random_fault_params_set_N_1`
4. 依次调用 `addComponentOutputMeasures` 添加：
   `_newBus_3p.Vrms`
   `SyncGeneratorRouter.PT_o`
   `SyncGeneratorRouter.wr_o`
   `SyncGeneratorRouter.theta_o`
5. `runProject`
6. `extract_and_check_data`

## 结果格式

- `submit_batch_simulation`
  返回 `task_id`
- `query_batch_simulation_status`
  返回中文键的状态字典，例如 `状态`、`总仿真数`、`已完成数`
- `get_batch_simulation_result`
  返回：
  `result_file`
  `result`
  `total_count`
  `returned_count`
  `truncated`
- 单个批次结果
  当前验证形态为：
  `final_result.check_result`
  `final_result.fault_info`
  可选包含 `files_results.save_flow_emt_hdf5.flow_url`
  可选包含 `files_results.save_flow_emt_hdf5.emt_url`

## 重要约束

- `get_step_temp()` 当前返回的是说明性模板，不是可直接提交的完整 JSON。
  其中 `generate_random_fault_params_set_N_1或setN_1_GroundFault` 是占位提示，实际提交时必须替换成真实 step 名称。
- 批量任务状态里的 `已完成数/失败数` 基于顶层结果项是否含 `error` 统计。
  判断单个工况是否真正完成，仍应检查 `result` 列表中的每条摘要。
- 本 skill 的通过标准是批量任务闭环和结构化摘要回收，不要求 HDF5 或 MinIO 落盘。

## 已验证脚本

- Python 直调版：`skills/batch-contingency-screening/scripts/verify_batch_contingency_screening.py`
