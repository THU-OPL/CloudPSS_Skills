# 仓库设计说明

## 一、目标

这个仓库不是一组零散的 skill 文件，而是 CloudPSS 团队的 skill 供给链。

它需要解决四个问题：

1. 贡献者如何按统一规范提交 skill
2. skill 如何声明触发条件、能力边界和运行依赖
3. 维护者如何判断 skill 是否可合并、可发布、可回归
4. skill 如何在删除历史私有目录后仍能单独使用和审核

## 二、借鉴 Claude Code 的部分

本仓库借鉴了 Claude / Anthropic skills 的一些核心模式：

- skill 是目录，不是单个文件
- `SKILL.md` 是主定义文件
- `SKILL.md` frontmatter 是人工维护的主元数据入口
- skill 采用渐进加载：metadata -> `SKILL.md` -> `scripts/` / `references/`
- skill 可以携带脚本
- skill 可以附带 eval 信息
- marketplace/catalog 可以由仓库侧工具补充生成

## 三、CloudPSS 的额外约束

CloudPSS 在公开技能组织方式之上额外增加一个强约束：

- 每个 skill 必须是独立资产

这意味着：

- 不能依赖 `psa/`
- 不能依赖 `CloudPSS_skillhub/`
- 不能 import 仓库外私有代码
- 当前版本不考虑 MCP

## 四、独立性策略

每个 skill 最小必须自带：

- `SKILL.md`

此外可以按需要补充：

- `requirements.txt`
- `evals/`
- `scripts/`
- `mylib/`

规则如下。

### 4.1 第三方依赖

- 如果 skill 需要 Python 第三方依赖，则写入 `requirements.txt`
- 只写这个 skill 真正需要的依赖
- 建议版本范围明确

### 4.2 私有代码

- 如果只是当前 skill 的少量私有 glue code，写入 `mylib/`
- 如果是多个 skill 共用、体积较大的 PSA 私有能力，应发布为独立版本化 Python 包
- skill 通过 `requirements.txt` 引用共享包，而不是依赖仓库内共享目录
- 不允许把整包旧代码直接 vendoring 进 skill

### 4.3 运行脚本

- `scripts/` 不是强制项
- 如果 skill 需要可重复执行的验证、导出、SDK 调用或其他确定性流程，建议提供 `scripts/`
- 脚本只应 import 标准库、第三方依赖和当前 skill 的 `mylib/`
- 不允许引用兄弟 skill
- 不允许引用仓库外目录

### 4.4 GitHub 共享包策略

- 共享私有包必须有独立仓库、独立版本和独立发布节奏
- `requirements.txt` 中可以使用 GitHub VCS 依赖
- 必须固定到不可变 ref，例如 tag 或 commit
- 不允许引用漂移分支，如 `main`、`master`

## 五、仓库治理层

虽然 skill 在运行时必须保持独立，但治理仍由仓库统一提供：

- `SKILL.md` frontmatter：唯一人工维护的 skill 元数据
- `catalog/skills-index.json`：由工具生成的技能索引
- 仓库 CLI：结构检查、索引生成、发布前检查

## 六、两类工具链

### 6.1 贡献者侧

贡献者工具负责“把 skill 写对”：

- 检查 `SKILL.md`
- 如果提供了依赖，则检查 `requirements.txt`
- 如果提供了 `mylib/`，检查它是否只承担本地私有 glue code
- 如果提供了 `evals/`，检查其结构和一致性
- 如果提供了 `scripts/`，检查其入口与声明是否自洽
- 通过仓库脚本运行本地提交前自检

### 6.2 维护者侧

维护者工具负责“把仓库管好”：

- 索引所有 skill
- 判断 skill 是否满足发布门禁
- 审核依赖是否失控
- 审核私有代码边界是否清晰
- 审核共享私有包是否已版本化且固定引用

## 七、推荐 Skill 类型

仓库中的 skill 推荐分为三类：

- `workflow`
- `analysis`
- `export`

当前模板示例覆盖：

- `model-fetch-and-branch`
- `power-flow-analysis`
- `emt-fault-study`
- `emt-simulation-workflow`

## 八、发布门禁

一个 skill 要进入 `published`，至少应满足：

- `SKILL.md` 合法
- skill 结构清晰、边界明确
- 如提供依赖，则依赖说明完整且可审计
- 如提供 `evals/`，其内容与 skill 对齐
- 如提供 `scripts/`，入口、用途与验证说明自洽
- `mylib/` 边界清晰，或明确采用共享私有包模式
- GitHub 共享依赖固定到 tag 或 commit
- catalog 生成成功
- 维护者 review 通过
