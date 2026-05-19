---
name: model-inspection-and-target-selection
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 巡检 CloudPSS 模型，确认当前潮流/电磁暂态方案与参数方案，从真实 revision 中发现母线、线路、发电机等目标对象，并把真实标签解析为可用于后续分析的 key。当用户需要先检查模型、确认故障对象、确认目标母线或线路、避免使用过期 label 时使用。
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
  category: inspection
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_model_inspection.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_sdk
---

# Model Inspection And Target Selection

## 何时使用

- 需要在做潮流、N-1、VSI、无功支撑分析前先确认模型状态。
- 需要查看当前 `SA_潮流计算`、`SA_电磁暂态仿真` 和 `SA_参数方案` 是否存在。
- 需要从真实模型中发现 bus、line、generator 的标签和 key。
- 需要把用户口中的标签解析成后续工具可直接使用的真实 key。

## 前置条件

- `.env` 已配置 `SIMSTUDIO_TOKEN` 和 `CLOUDPSS_API_URL`。
- 默认模型使用 `model/yuanxuefeng/IEEE39`。
- 运行时依赖 `cloudpss-psa-core` 提供的 `psa.tool_box.PowerSystemAnalysis`。

## 工具选择规则

- `getCurrentJob` / `getCurrentConfig`
  用于巡检当前计算方案和参数方案。
- `getRevision`
  用于读取真实模型 revision，再由 agent 自行过滤出 bus、line、generator。
  这是当前最稳妥的巡检入口。
- `convertLabelToKey`
  当你已经从 revision 中选定真实标签后，用它解析为后续分析需要的 key。
- `refreshTopology` / `generateNetwork`
  仅用于高级拓扑预检查。
  当前核心目标发现流程仍应优先基于 `getRevision`，不要把拓扑图生成当成主入口。

## 标准流程

### 1. 初始化模型

1. 调用 `initModelAndCreateSACanvas(cloudpss_model="model/yuanxuefeng/IEEE39")`
2. 确认返回包含：
   `SA_潮流计算`
   `SA_电磁暂态仿真`
   `SA_参数方案`

### 2. 巡检当前方案

1. 调用 `getCurrentJob(stype="power-flow", jobName="SA_潮流计算")`
2. 调用 `getCurrentJob(stype="emtps", jobName="SA_电磁暂态仿真")`
3. 调用 `getCurrentConfig(configName="SA_参数方案")`

如果这一步拿不到方案，不要继续做下游分析。

### 3. 从真实 revision 发现目标对象

1. 调用 `getRevision()`
2. 从 `revision["implements"]["diagram"]["cells"]` 中筛选真实组件
3. 常用筛选方式：
   - 母线：`definition == "model/CloudPSS/_newBus_3p"`
   - 发电机：`definition == "model/CloudPSS/SyncGeneratorRouter"`
   - 线路：优先看真实 `label`，例如 `TLine_3p-*`
4. 先从真实 revision 中拿到标签，再进入下一步解析 key

### 4. 把真实标签解析为 key

1. 从 revision 中选定目标标签
2. 调用 `convertLabelToKey(labels=[...])`
3. 将返回的 key 用于后续故障设置、量测配置或对象筛选

### 5. 可选的拓扑预检查

1. 调用 `refreshTopology()`
2. 调用 `generateNetwork(show=False)`

这一组调用用于确认拓扑图缓存可构建。
核心目标发现仍以 `getRevision` 为准。

## 结果格式

- `getCurrentJob`
  返回 `List[Dict]`
  每个元素为一个已解析的计算方案字典
- `getCurrentConfig`
  返回 `List[Dict]`
  每个元素包含方案名称和参数配置
- `getRevision`
  返回当前项目 revision 的 JSON
  真实组件信息在 `revision["implements"]["diagram"]["cells"]`
- `convertLabelToKey`
  返回 `{"busKeys": [...]}`  
  字段名虽然叫 `busKeys`，但也可用于发电机、线路等标签解析；实际含义应理解为“解析出的组件 key 列表”

## 重要约束

- 若只是为了对象发现，优先使用 `getRevision`，不要先写死线路名或母线名。
- `convertLabelToKey` 只能解析已经在真实模型中存在的标签。
- `refreshTopology` / `generateNetwork` 目前更适合作为预检查，不要替代 revision 巡检主流程。
- 若需要更细的参数条件筛选，可以继续使用 `screenCompByArg`；当前核心流程不依赖它。

## 已验证脚本

- Python 直调版：`skills/model-inspection-and-target-selection/scripts/verify_model_inspection.py`

验证脚本的验证目标是：

- 巡检真实方案
- 从真实 revision 发现目标对象
- 解析真实标签到 key
- 完成拓扑预检查
