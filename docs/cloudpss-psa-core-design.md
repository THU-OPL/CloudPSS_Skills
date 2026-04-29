# cloudpss-psa-core 设计说明

## 一、设计目标

`cloudpss-psa-core` 是面向 CloudPSS 团队 skill 的共享私有 Python 包，用来承载多个 PSA 相关 skill 都会重复用到的基础能力。

它存在的主要原因是：

- 避免把大段 PSA helper 代码复制到每个 skill 中
- 为 CloudPSS SDK 提供更稳定的兼容封装层
- 为多个 skill 提供统一的 token、model、job、result 工具能力
- 让共享逻辑独立版本化，而不是跟随 skill 仓库一起无边界扩张

## 二、什么适合放进共享包

适合进入 `cloudpss-psa-core` 的内容：

- token 加载与 CloudPSS SDK 配置
- model 加载、fetch-or-load helper
- job 轮询与 timeout 处理
- 通用结果表归一化
- 通用模型摘要 helper
- 多个 skill 都会重复使用的稳定 PSA workflow wrapper

不适合放进共享包的内容：

- 只服务于单个 skill 的一次性 study 参数
- 面向 skill 的 prompt 或说明文本
- 单个 skill 特有的报告格式化逻辑
- 只对某一个 benchmark 模型成立的场景常量

判断原则很简单：  
如果一段逻辑只对一个 skill 有意义，就不应进入共享包。

## 三、推荐仓库结构

共享包推荐采用如下结构：

```text
cloudpss-psa-core/
├── src/psa/
│   ├── tool_box/
│   └── utils/
├── tests/
│   ├── test_tables.py
│   └── test_metadata.py
├── pyproject.toml
├── README.md
└── LICENSE
```

这里的核心思想是：

- `src/psa/` 暴露稳定运行时边界
- `tests/` 验证表格解析、元数据处理等共享逻辑
- skill 仓库通过依赖包版本来复用能力，而不是直接复制源码

## 四、版本策略

建议使用语义化版本：

- `MAJOR`：有破坏性 API 或行为变化，需要 skill 适配
- `MINOR`：新增向后兼容 helper 或 wrapper
- `PATCH`：bugfix、表格解析修复、timeout 修复、文档修复

推荐的发布策略：

- `published` 状态的 skill 应固定到正式 tag，例如 `v0.3.1`
- 内部实验性 skill 可以固定到 commit hash
- 已发布 skill 不应依赖浮动分支

## 五、Skill 的接入方式

skill 接入共享包，建议使用两种策略之一。

### 1. `shared-package`

适用场景：  
这个 skill 所需的可复用私有逻辑，全部都可以从共享包获得。

要求：

- `requirements.txt` 中声明 `cloudpss-psa-core @ git+...@vX.Y.Z`
- 不再保留 `mylib/`
- `SKILL.md` 中设置 `dependency_strategy: shared-package`

### 2. `hybrid`

适用场景：  
这个 skill 同时需要共享 PSA 能力和少量本地场景 glue code。

要求：

- `requirements.txt` 中声明 `cloudpss-psa-core @ git+...@vX.Y.Z`
- `mylib/` 只保留 skill 特有场景逻辑
- `SKILL.md` 中设置 `dependency_strategy: hybrid`

## 六、运行时边界

共享包应该对外暴露稳定的 `psa.*` 运行时边界，例如：

- `psa.tool_box.PowerSystemAnalysis`
- `psa.tool_box.CaseEditToolbox`
- `psa.utils.*`

skill 应直接依赖这个 GitHub 包，并从 `psa.*` 导入。  
不应再把 PSA runtime 代码复制进每个 skill 的本地目录。

## 七、主要风险

如果治理不好，`cloudpss-psa-core` 会出现几个明显风险：

- 如果把过多模型专属 study 逻辑塞进去，它会重新变成第二个单体仓库
- 如果 API 过于底层，skill 仍然会在外层重复包装同样的逻辑
- 如果已发布 skill 只固定 commit、不固定版本 tag，维护者会失去清晰的发布语义

因此共享包必须保持：

- 边界稳定
- 功能收敛
- 面向复用，而不是面向单个场景

## 八、结论

`cloudpss-psa-core` 的定位应当是：

- skill 的版本化 PSA 运行时共享包
- 多 skill 复用能力的统一承载点
- CloudPSS SDK 上方的稳定封装层

它不应成为：

- 单个 skill 的临时逻辑堆放区
- 另一个无限扩张的私有大仓库
- 规避 skill 边界治理的后门
