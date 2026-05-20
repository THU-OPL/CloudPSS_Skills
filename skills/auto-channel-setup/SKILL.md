---
name: auto-channel-setup
description: 使用 CloudPSS SDK 对 EMT-ready 模型自动巡检输出通道和 EMT job 的 output_channels 配置，在本地工作副本中重组或补齐量测输出分组，并通过真实 CloudPSS EMT 仿真验证通道配置可以产生可读取波形。当用户需要自动配置 EMT 输出通道、检查量测通道覆盖、调整通道采样频率或为波形导出准备仿真输出时使用。
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
  category: workflow
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_auto_channel_setup.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_emt_channel_setup
---

# Auto Channel Setup

## When to use

- 需要在 EMT 仿真前检查模型已有的 `_newChannel` 输出通道。
- 需要确认 EMT job 的 `output_channels` 是否覆盖目标通道。
- 需要在不保存远端模型的前提下，构造本地工作副本并重组输出通道分组。
- 需要为 `waveform-export`、`comtrade-export` 或结果对比准备真实 CloudPSS 波形。

## Workflow

1. 加载 CloudPSS token 和目标模型；公开使用时通过 `CLOUDPSS_TEST_EMT_MODEL_RID` 或命令行传入自己账号下的 EMT-ready 模型。
2. 如果账号下没有 IEEE3 EMT 样例，先从官方 `model/CloudPSS/IEEE3` 保存或构建到自己账号，再传入该新 RID。
3. 巡检模型中的 `_newChannel` 元件，读取通道名称、维度、采样频率和 EMT job 输出分组。
4. 在本地工作副本中选择目标通道，更新 EMT job 的 `output_channels`。
5. 调用 `runEMT()` 执行真实 CloudPSS 仿真。
6. 读取 `job.result`，校验目标 plot 和 channel 数据可访问。

## Output

- 模型 RID、模型名称和 EMT job 名称。
- 通道清单、输出分组和未映射通道列表。
- 本地工作副本配置的目标通道、采样频率和分组名称。
- 真实 EMT 仿真的 job id、plot 摘要和目标通道采样点数。

## Constraints

- 不调用 `model.save()`，不会保存远端模型修改。
- 当前实现面向已有 `_newChannel` 元件的模型；如果模型没有任何通道，需要先补充通道元件或提供更完整的模型编辑接口。
- 输出通道分组通过本地工作副本的 EMT job args 修改，验证通过真实 `runEMT()` 结果确认。
- 如果目标模型没有 EMT topology 或 `runEMT()` 失败，验证脚本直接失败。
- 本仓库验证曾使用私有账号下的 EMT-ready IEEE3 副本；公开 skill 不依赖该账号，用户必须替换为自己的模型 RID。

## Verified script

- `skills/auto-channel-setup/scripts/verify_auto_channel_setup.py`
