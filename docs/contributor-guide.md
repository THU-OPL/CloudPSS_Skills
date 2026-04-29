# 贡献者指南

## 一、Skill 目录结构要求

每个贡献进仓库的 skill 都必须直接放在 `skills/<skill-id>/` 下。

最小必需内容是：

```text
skills/<skill-id>/
└── SKILL.md
```

常见的可选补充内容包括：

```text
skills/<skill-id>/
├── requirements.txt
├── evals/
│   └── evals.json
├── scripts/
│   └── verify_<skill>.py
└── mylib/
```

不要提交这种多套一层目录的结构：

```text
skills/<skill-id>/<skill-id>/...
```

这是最常见、也最容易被 CI 直接拦下的错误。

## 二、必须提供的文件

### 1. `SKILL.md`

`SKILL.md` 是面向模型和 reviewer 的主定义文件，应包含：

- YAML frontmatter
- skill 的触发描述
- 适用场景
- 已验证的工作流
- 输出形式
- 关键约束
- 验证入口说明

frontmatter 中通常至少应有：

- `name`
- `description`
- `compatibility`
- `metadata`

### 2. `requirements.txt`

如果这个 skill 需要 Python 第三方依赖，则提供 `requirements.txt`。

约束：

- 只写这个 skill 真正需要的依赖
- 不依赖仓库外的私有源码目录
- 尽量写明确的版本范围
- 如果依赖 GitHub 上的共享包，必须固定到 tag 或 commit，不允许引用浮动分支如 `main`、`master`，参考skills/power-flow-analysis/requirements.txt

### 3. `evals/evals.json`

如果这个 skill 需要结构化 eval 描述，则提供 `evals/evals.json`，通常包含：

- `skill_name`
- 一个或多个 eval 用例
- 预期输出
- 验收标准或 expectations

### 4. `scripts/verify_<skill>.py`

脚本不是强制项。

如果这个 skill 需要本地可重复执行的验证、导出、调用 SDK 或其他确定性流程，建议在 `scripts/` 下提供验证脚本。

命名约定：

```text
verify_<skill>.py
```

### 5. `mylib/`

如果 skill 需要少量本地私有 glue code，可以放在 `mylib/` 下；如果只是纯 `SKILL.md` 指导型 skill，可以不提供。

约束：

- 只保留这个 skill 必需的最小代码
- 不要把大段外部代码直接复制进来
- 不要 import 仓库外私有路径
- 不要把 `mylib/` 变成隐式共享 SDK

## 三、什么时候应该抽共享包

如果多个 skill 复用同一类 PSA 私有能力，优先抽成独立 Python 包，而不是在多个 skill 下复制逻辑。

适合抽到共享包的能力包括：

- token 加载与 CloudPSS SDK 配置
- model fetch/load helper
- job 轮询与 timeout helper
- 通用结果表归一化
- 多个 skill 复用的 PSA wrapper

如果使用共享包，应满足：

- 在独立仓库中维护
- 有明确版本
- 在 `requirements.txt` 中声明
- GitHub VCS 依赖固定到 tag 或 commit
- 在 `SKILL.md` 的 `metadata.shared_packages` 中声明包名

示例：

```text
cloudpss>=4.5.28
cloudpss-psa-core @ git+https://github.com/your-org/cloudpss-psa-core.git@v0.3.1
```

或固定到 commit：

```text
cloudpss-psa-core @ git+https://github.com/your-org/cloudpss-psa-core.git@8f3c1d2
```

## 四、编写原则

- 只写已经真实验证过的 workflow
- 不要在 `SKILL.md` 里声明尚未跑通的能力
- 如果底层逻辑不稳定，先修 `mylib/` 或共享包，再写 skill
- 如果依赖 CloudPSS SDK，直接在 skill 自己的 `requirements.txt` 中声明
- skill 必须在删除仓库外私有目录后仍然可理解、可验证、可维护

## 五、提交前本地自检

在发 PR 之前，必须先在仓库根目录运行本地检查。

### 推荐方式：一条命令

```powershell
python scripts/check_skill.py <skill-id>
```

例如：

```powershell
python scripts/check_skill.py emt-simulation-workflow
```

这条命令会自动检查：

- skill 最小目录结构是否成立
- 是否误套一层 `skills/<skill-id>/<skill-id>/...`
- 是否误带 `.env`、`.cloudpss_token`
- 是否误带 `artifacts/`、`__pycache__/`
- `validate-skill` 是否通过
- 仓库级 `release-check` 是否通过

### 直接运行底层 CLI

如果你想手动逐条运行，也可以执行：

```powershell
python -m pip install -e .
python -m src.cloudpss_skillrepo validate-skill skills/<skill-id>
python -m src.cloudpss_skillrepo release-check
```

不要直接运行 `src/cloudpss_skillrepo/cli.py`。  
统一使用模块入口 `python -m src.cloudpss_skillrepo ...`，这样本地行为和 GitHub Actions 一致。

## 六、推荐提交流程

1. 创建 `skills/<skill-id>/`
2. 编写 `SKILL.md`
3. 如果需要，补充 `requirements.txt`
4. 如果需要，添加 `mylib/`
5. 如果需要，编写 `evals/evals.json`
6. 如果需要，编写 `scripts/verify_<skill>.py`
7. 运行 `python scripts/check_skill.py <skill-id>`
8. 修复所有本地检查问题
9. 提交 PR

## 七、禁止提交的内容

以下内容不应进入仓库：

- `.env`
- `.cloudpss_token`
- `artifacts/`
- `__pycache__/`
- 本地 IDE 文件
- 仅用于个人调试的临时输出文件

## 八、常见错误

- `SKILL.md` 缺少 `name` 或 `description`
- `SKILL.md` 中缺少必要 metadata 字段
- `evals.skill_name` 与 skill 目录名不一致
- 缺少 `requirements.txt`
- GitHub 共享依赖没有固定到 tag 或 commit
- 验证脚本仍依赖仓库外私有代码
- PSA 私有代码被复制到多个 skill，而不是抽成共享包
- skill 目录被错误写成 `skills/<skill-id>/<skill-id>/...`
