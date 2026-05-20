---
name: comtrade-export
description: 使用 CloudPSS SDK 从真实 EMT 仿真结果读取波形通道，并导出为 COMTRADE `.cfg` 与 `.dat` 文件，校验通道数、采样率、样本数和数据行完整性。当用户需要把 CloudPSS EMT 波形转换为 COMTRADE、用于继保/暂态数据交换、生成标准暂态记录文件或校验导出文件结构时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Set CLOUDPSS_TEST_EMT_MODEL_RID or pass an EMT-ready model RID under your own account. Verification refuses placeholder and model/holdme/* sources.
metadata:
  owner: cloudpss-team
  category: export
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_comtrade_export.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_comtrade_export
---

# Comtrade Export

## When to use

- 需要把 CloudPSS EMT 波形导出为 COMTRADE 标准交换文件。
- 需要生成 `.cfg` 和 `.dat` 文件，供继电保护、暂态分析或第三方工具读取。
- 需要对导出文件进行基础结构校验，例如通道数、采样率和样本行数。

## Workflow

1. 加载 token 和 EMT-ready 模型；公开使用时通过 `CLOUDPSS_TEST_EMT_MODEL_RID` 或命令行传入自己账号下的模型 RID。
2. 拒绝 `model/holdme/...` 验证源。
3. 执行真实 CloudPSS `runEMT()` 并读取 `job.result`。
4. 选取一个 plot 的若干 channel，读取 `x/y` 波形。
5. 生成 COMTRADE 1999 ASCII `.cfg` 和 `.dat` 文件。
6. 校验 `.cfg` 通道数、`.dat` 样本行数和每行字段数。

## Output

- CloudPSS job id、源模型 RID 和源 plot。
- COMTRADE `.cfg` 与 `.dat` 文件路径。
- 导出通道数、样本数、估算采样率和通道统计。

## Constraints

- 默认导出 ASCII DAT，便于审查和跨平台校验；需要 BINARY 时应在确认消费端要求后再扩展。
- 当前只导出模拟量通道，不生成数字量通道。
- 通道单位和相别基于名称启发式推断，工程报告中应注明需要用户复核。
- 该 skill 不保存远端模型修改。
- 如果账号下没有 IEEE3 EMT 样例，先从官方 `model/CloudPSS/IEEE3` 保存或构建到自己账号，再传入该新 RID；本仓库实测使用的是私有 EMT-ready 副本，不作为公开默认值。

## Verified script

- `skills/comtrade-export/scripts/verify_comtrade_export.py`
