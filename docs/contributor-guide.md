# Contributor Guide

## 提交一个新 skill 的最低要求

每个 skill 目录至少包含：

```text
skills/<skill-id>/
├─ SKILL.md
├─ requirements.txt
├─ evals/evals.json
├─ mylib/                  # 可选
└─ scripts/
   └─ verify_<skill>.py
```

## 你需要写什么

### 1. `SKILL.md`

面向模型与 reviewer，内容包括：

- frontmatter 中写入 name、description、compatibility、metadata 等信息
- 何时使用
- 标准流程
- 输出格式
- 重要约束
- 已验证脚本

### 2. `requirements.txt`

用于声明这个 skill 的第三方 Python 依赖。

原则：

- 只写真正需要的包
- 不依赖仓库外私有代码
- 版本范围尽量明确
- 如果使用 GitHub 私有共享包，固定到 tag 或 commit，不要引用 `main` / `master`

### 4. `mylib/`

如果 skill 只需要少量本地私有逻辑，可以直接放进自己的 `mylib/`。

要求：

- 只保留最小必要代码
- 不要整包复制旧仓库
- 不要从仓库外路径 import

### 4.1 共享私有包

如果多个 skill 复用同一套 PSA 私有能力，优先做成独立 Python 包。

要求：

- 单独仓库维护
- 有明确版本
- 在 `requirements.txt` 中引用
- GitHub VCS 依赖固定到 tag 或 commit
- 在 `SKILL.md` 的 `metadata.shared_packages` 中登记包名

示例：

```text
cloudpss>=4.5.28
cloudpss-psa-core @ git+https://github.com/your-org/cloudpss-psa-core.git@v0.3.1
```

或者固定到 commit：

```text
cloudpss-psa-core @ git+https://github.com/your-org/cloudpss-psa-core.git@8f3c1d2
```

### 3. `evals/evals.json`

至少包含：

- skill 名称
- 1 个以上真实 eval
- 预期输出
- pass criteria / expectations

### 4. `scripts/`

脚本命名遵守：

- `verify_<skill>.py`

## 编写原则

- 只写已经真实验证过的流程
- 不要在 `SKILL.md` 里写想象中的能力
- 如果底层逻辑不稳定，先修 `mylib/`，再写 skill
- 如果用到 CloudPSS SDK，直接在 skill 的 `requirements.txt` 中写明

## 提交流程

1. 新建 skill 目录
2. 填写 `SKILL.md`
3. 填写 `requirements.txt`
4. 如有需要，写 `mylib/`
5. 填写 `evals/evals.json`
6. 补充验证脚本
7. 运行本地校验
8. 提交 PR

## 本地校验

```powershell
python -m src.cloudpss_skillrepo validate-skill skills/<skill-id>
python -m src.cloudpss_skillrepo package-skill skills/<skill-id>
```

## 常见错误

- `SKILL.md` frontmatter 缺少 `name` 或 `description`
- `SKILL.md metadata` 中缺少 `owner`、`category`、`entrypoint` 等必要字段
- `evals.skill_name` 与 skill id 不一致
- 缺少 `requirements.txt`
- GitHub 共享包依赖没有固定版本
- 脚本仍依赖仓库外私有代码
- 共享 PSA 代码仍以复制目录方式散落在多个 skill 中
