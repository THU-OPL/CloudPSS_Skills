# Repository Design

## 1. 目标

这个仓库不是 skill 文件集合，而是 CloudPSS 团队的 skill 供应链。

它需要解决四个问题：

1. 贡献者如何按统一规范提交 skill
2. skill 如何声明触发条件、能力边界和运行依赖
3. 维护者如何判断 skill 是否可合并、可发布、可回归
4. skill 如何在删除历史目录后仍可单独使用

## 2. 参考 Claude Code 的地方

本仓库借鉴 Claude / Anthropic 的核心模式：

- skill 是目录，不是单文件
- `SKILL.md` 是一等公民
- `SKILL.md` frontmatter 是唯一的人工元数据入口
- skill 采用渐进加载：metadata -> `SKILL.md` -> `scripts/` / `references/`
- skill 允许携带脚本
- skill 需要 evals
- marketplace 需要额外索引元数据

## 3. CloudPSS 的额外约束

CloudPSS 这里增加一个强约束：

- 每个 skill 必须是独立资产

这意味着：

- 不能依赖 `psa/`
- 不能依赖 `CloudPSS_skillhub/`
- 不能 import 仓库外私有代码
- 当前版本不考虑 MCP

## 4. 独立性策略

每个 skill 必须自带：

- `requirements.txt`
- `scripts/`

并且可以按需要携带：

- `mylib/`

规则如下：

### 4.1 第三方依赖

- 写入 `requirements.txt`
- 只写该 skill 真正需要的包
- 建议版本范围明确

### 4.2 私有代码

- 如果只是当前 skill 的少量私有 glue code，写入 `mylib/`
- 如果是多个 skill 共用、体积较大的 PSA 私有能力，发布为独立版本化 Python 包
- skill 通过 `requirements.txt` 引用该共享包，而不是依赖仓库内共享目录
- 不允许“整仓 vendoring”

### 4.3 运行脚本

- 只 import 标准库、第三方依赖、当前 skill 的 `mylib/`
- 不允许引用兄弟 skill
- 不允许引用仓库外目录

### 4.4 GitHub 共享包策略

- 共享私有包必须有独立仓库、独立版本和独立发布节奏
- `requirements.txt` 中可以使用 GitHub VCS 依赖
- 必须固定到不可变 ref，例如 tag 或 commit
- 不允许引用漂移分支，如 `main`、`master`

## 5. 仓库治理层

虽然运行时必须按 skill 独立，但治理仍然由仓库统一提供：

- `SKILL.md` frontmatter：唯一人工维护的 skill 元数据
- `catalog/skills-index.json`：由工具生成的技能索引
- 仓库 CLI：结构检查、索引生成、发布前检查

## 6. 两类工具链

### 6.1 贡献者侧

贡献者工具负责“把 skill 写对”：

- 检查 `SKILL.md`
- 检查 `requirements.txt`
- 检查 `mylib/` 是否只承担本地私有 glue code
- 检查 `evals/`
- 打包独立 skill 分发物

### 6.2 维护者侧

维护者工具负责“把仓库管好”：

- 索引所有 skill
- 判断 skill 是否满足发布门禁
- 审核依赖是否失控
- 审核私有代码边界是否清晰
- 审核共享私有包是否已版本化且引用固定

## 7. 推荐 skill 类型

仓库内的 skill 推荐分三类：

- `workflow`
- `analysis`
- `export`

当前样板示例覆盖：

- `model-fetch-and-branch`
- `powerflow-engineering-study`
- `emt-fault-study`

## 8. 发布门禁

一个 skill 进入 `published`，至少满足：

- `SKILL.md` 合法
- `requirements.txt` 存在
- `evals/evals.json` 存在
- `scripts/verify_<skill>.py` 存在
- `mylib/` 边界清晰，或明确采用共享私有包模式
- GitHub 共享依赖固定到 tag 或 commit
- catalog 生成成功
- 维护者 review 通过
