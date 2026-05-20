---
name: topology-and-model-audit
description: 使用 cloudpss-psa-core 中兼容 psa.* 导入路径的 PowerSystemAnalysis 对 CloudPSS 模型执行拓扑和模型有效性审计，从真实 revision 构建连接图并运行真实潮流验证模型可执行，识别孤立组件、悬空连接、重复标签、缺失标签和关键元件数量异常。当用户需要检查模型拓扑、孤岛、悬空节点、连接完整性、模型质量或下游仿真前预检查时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
  notes: Uses the versioned cloudpss-psa-core shared package; the live verification reads the real revision and runs CloudPSS power flow. CloudPSS ModelTopology API is optional because some deployments do not expose it.
metadata:
  owner: cloudpss-team
  category: inspection
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_topology_and_model_audit.py
  dependency_strategy: shared-package
  shared_packages:
    - cloudpss-psa-core
  verification_method: direct_cloudpss_revision_topology_and_powerflow
---

# Topology And Model Audit

## When to use

- 需要在潮流、暂态、VSI、N-1 或批量研究前确认模型拓扑可构建。
- 需要识别孤立母线、无连接组件、悬空拓扑引脚、重复标签或空标签。
- 需要统计母线、线路、变压器、发电机、负荷和量测通道数量。
- 需要判断真实 CloudPSS revision 的连接关系是否足以支持下游仿真。

## Workflow

1. 调用 `initModelAndCreateSACanvas(cloudpss_model=...)` 初始化真实模型。
2. 调用 `getRevision()` 读取 revision，按 `definition` 和 `shape` 统计组件。
3. 从 revision 的 `diagram-edge` 连接关系构建组件连接图。
4. 计算组件数、连接边数、孤立顶点、悬空连接、重复标签和空标签。
5. 调用真实 `runProject` 执行潮流计算，验证模型不只是可读取，而且可仿真。
6. 如果部署支持 `refreshTopology()`，可作为额外拓扑 API 交叉检查；当前标准验证不强依赖该 API。
7. 输出可机器读取的审计摘要；若关键数量为 0、连接图为空或潮流不收敛，应停止下游仿真。

## Output

- `revision_inventory`: revision 中按组件类型统计的库存。
- `topology_summary`: revision 连接图的组件数、图边数、孤立组件和悬空连接。
- `power_flow_validation`: 真实潮流运行结果和母线电压摘要。
- `model_quality`: 空标签、重复标签、孤立组件、悬空引脚和关键组件计数。
- `pass`: 是否满足下游仿真的最低拓扑条件。

## Constraints

- 默认验证模型为 `model/CloudPSS/IEEE39`。
- 当前审计基于真实 revision 连接关系；若 CloudPSS `ModelTopology` GraphQL 在部署中可用，可额外启用拓扑 API 检查。
- 孤立组件不一定都是错误，辅助信号、控制元件或未接入的临时画布组件需要结合工程语义判断。
- 不在 skill 内复制旧 PSA 仓库逻辑，统一使用 `cloudpss-psa-core`。

## Verified script

- `skills/topology-and-model-audit/scripts/verify_topology_and_model_audit.py`

