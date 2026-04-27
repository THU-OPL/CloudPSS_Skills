# CloudPSS Agent Skills

CloudPSS 团队内部 skill 仓库样板，参考 Claude Code / Anthropic Skills 的组织方式，但采用更严格的独立性约束：

- 每个 skill 必须独立可迁移
- 不能依赖仓库外的私有目录
- Python 第三方依赖必须在 skill 目录内说明
- 共享私有能力应发布为独立版本化 Python 包，再由 skill 在 `requirements.txt` 中引用
- `mylib/` 只保留该 skill 自己的少量私有 glue code
- 当前版本不考虑 MCP 服务

## 面向两类角色

- 贡献者：编写、验证、打包、提交 skill
- 维护者：审核、分级、发布、回归验证 skill

## 仓库结构

```text
.
├─ .cloudpss-plugin/        # Marketplace / catalog 元数据
├─ catalog/                 # 技能索引与发布清单
├─ docs/                    # 贡献规范、架构、审核标准
├─ skills/                  # skill 实体目录
├─ src/cloudpss_skillrepo/  # 仓库工具 CLI
└─ templates/skill/         # 新 skill 模板
```

## 单个 skill 的标准结构

```text
skills/<skill-id>/
├─ SKILL.md
├─ requirements.txt
├─ evals/
│  └─ evals.json
├─ mylib/                  # 可选，仅当该 skill 需要本地私有 glue code
│  └─ ...
└─ scripts/
   └─ verify_<skill>.py
```

## 设计原则

- `SKILL.md` 面向模型与 reviewer，只保留 `name` 和 `description` 两个 frontmatter 字段
- `SKILL.md` frontmatter 同时承载 skill 触发信息与轻量治理元数据
- `requirements.txt` 面向依赖声明
- `mylib/` 面向 skill 私有 glue code，不承载跨 skill 共享库
- `scripts/` 面向可重复验证

## 两类工具

### 贡献者工具

- `validate-skill`：检查 frontmatter、manifest、目录结构
- `package-skill`：打包 skill 分发物

### 维护者工具

- `index-skills`：重建 catalog
- `release-check`：检查候选 skill 是否满足发布门禁
- `list-skills`：查看当前仓库已发现的 skill

## 快速开始

```powershell
cd cloudpss-agent-skills
python -m src.cloudpss_skillrepo validate-skill skills\model-fetch-and-branch
python -m src.cloudpss_skillrepo package-skill skills\model-fetch-and-branch
python -m src.cloudpss_skillrepo index-skills
```

## 样板示例

当前提供 3 个独立 skill 示例：

- `model-fetch-and-branch`
- `powerflow-engineering-study`
- `emt-fault-study`

它们都以 `cloudpss` SDK 为直接依赖，不依赖 `psa/` 或 `CloudPSS_skillhub/`。

## 参考来源

- Claude Code skills 文档
- Anthropic 公开 skills 仓库

具体落地说明见：

- `docs/repository-design.md`
- `docs/claude-code-alignment.md`
- `docs/contributor-guide.md`
- `docs/maintainer-guide.md`
