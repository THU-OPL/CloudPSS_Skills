# CloudPSS Agent Skills

CloudPSS Agent Skills 是 CloudPSS 团队内部的 skill 仓库模板。  
它参考了 Claude Code / Anthropic Skills 的组织方式，但在可迁移性、依赖透明度和仓库治理上更严格。

核心约束：

- 每个 skill 必须能独立理解和审核
- 不能依赖仓库外的私有源码目录
- Python 第三方依赖应在 skill 自己的 `requirements.txt` 中声明
- 多个 skill 共用的大块私有能力应抽成独立版本包
- `mylib/` 只用于 skill 私有的最小 glue code
- 当前版本不引入 MCP 运行时假设

## 面向的角色

- 贡献者：编写、验证、提交 skill
- 维护者：审核、分级、发布、做回归检查

## 仓库结构

```text
.
├── .cloudpss-plugin/        # Marketplace / catalog 元数据
├── catalog/                 # 技能索引与发布清单
├── docs/                    # 贡献规范、架构说明、审核标准
├── scripts/                 # 仓库级辅助脚本
├── skills/                  # skill 实体目录
├── src/cloudpss_skillrepo/  # 仓库工具 CLI
└── templates/skill/         # 新 skill 模板
```

## 单个 Skill 的推荐结构

最小必需内容：

```text
skills/<skill-id>/
└── SKILL.md
```

常见的可选补充内容：

```text
skills/<skill-id>/
├── requirements.txt
├── evals/
│   └── evals.json
├── mylib/                  # 可选，仅当 skill 需要本地私有 glue code
└── scripts/
    └── verify_<skill>.py  # 可选，用于可重复验证或确定性执行
```

## 设计原则

- `SKILL.md` 是面向模型和 reviewer 的主定义文件
- `SKILL.md` frontmatter 同时承载 skill 触发信息和轻量治理元数据
- `requirements.txt` 用于声明 Python 依赖，可按需提供
- `mylib/` 用于承载 skill 私有 glue code，不应用来替代共享包
- `scripts/` 用于可重复执行的验证、导出或 SDK 调用流程，但不是强制项

## 仓库工具

### 贡献者常用工具

- `validate-skill`：检查单个 skill 的结构、frontmatter 和治理字段
- `package-skill`：将 skill 打包成可分发的 `.skill`
- `scripts/check_skill.py`：在提交前运行本地自检

### 维护者常用工具

- `index-skills`：重建 catalog
- `release-check`：检查仓库中的 skill 是否满足发布门禁
- `list-skills`：查看仓库已发现的 skill

## 快速开始

在仓库根目录执行：

```powershell
python -m pip install -e .
python scripts/check_skill.py model-fetch-and-branch
python -m src.cloudpss_skillrepo validate-skill skills/model-fetch-and-branch
python -m src.cloudpss_skillrepo index-skills
```

如果你只想运行仓库 CLI，也可以直接执行：

```powershell
python -m src.cloudpss_skillrepo validate-skill skills/model-fetch-and-branch
python -m src.cloudpss_skillrepo package-skill skills/model-fetch-and-branch
python -m src.cloudpss_skillrepo index-skills
```

## 当前示例 Skill

当前仓库包含 4 个示例 skill：

- `model-fetch-and-branch`
- `power-flow-analysis`
- `emt-fault-study`
- `emt-simulation-workflow`

这些示例以 CloudPSS SDK 或最小本地 `mylib/` 为基础，不依赖 `psa/` 或 `CloudPSS_skillhub/` 外部目录。

## 相关文档

- [docs/repository-design.md](docs/repository-design.md)
- [docs/claude-code-alignment.md](docs/claude-code-alignment.md)
- [docs/cloudpss-psa-core-design.md](docs/cloudpss-psa-core-design.md)
- [docs/contributor-guide.md](docs/contributor-guide.md)
- [docs/maintainer-guide.md](docs/maintainer-guide.md)
