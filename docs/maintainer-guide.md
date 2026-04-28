# Maintainer Guide

## 维护者的职责

维护者不只是看文档是否完整，而是对 skill 的真实性、稳定性和可治理性负责。

每个 skill 需要回答：

1. 触发边界是否清晰
2. 运行前提是否明确
3. 依赖是否独立
4. 结果是否可信
5. 是否适合进入共享 catalog

## 维护者检查清单

- 目录结构完整
- `SKILL.md` frontmatter 合法
- `SKILL.md` frontmatter 包含必要治理字段
- `requirements.txt` 存在
- `evals/evals.json` 存在且与 skill 对齐
- `scripts/verify_<skill>.py` 存在
- `mylib/` 边界清晰，或明确不使用 `mylib/`
- GitHub 共享包依赖已固定到 tag 或 commit
- 未验证边界写清楚

## 质量等级建议

- `draft`：仅文档草稿，无真实验证
- `experimental`：有最小验证，但覆盖不足
- `validated`：真实脚本链路已验证
- `published`：满足发布门禁，可进入团队共享目录

## 维护者工具

### 重建索引

```powershell
python -m src.cloudpss_skillrepo index-skills
```

### 校验单个 skill

```powershell
python -m src.cloudpss_skillrepo validate-skill skills/<skill-id>
```

### 发布前检查

```powershell
python -m src.cloudpss_skillrepo release-check
```

## 依赖治理原则

- 每个 skill 自带依赖说明
- 第三方依赖写入 `requirements.txt`
- 当前 skill 自己的少量私有逻辑写入 `mylib/`
- 多个 skill 共享的 PSA 私有能力优先拆成独立版本化 Python 包
- `cloudpss-psa-core` 这类共享包应保持小而稳定，不承载单个 skill 的场景特化逻辑
- 需要环境变量时，必须写入 `compatibility.required_env_vars`
- 需要外部服务时，必须写入 `compatibility.notes`

## 回归建议

对于核心 skill，至少按以下维度建回归：

- model / branch 管理类
- 单次分析类
- 导出 / 研究报告类

当前样板推荐的三类基准样本：

- `model-fetch-and-branch`
- `power-flow-analysis`
- `emt-fault-study`
