# Agent 创建 CloudPSS Skill 指南

本文档用于指导 Agent 在本仓库中创建、提取或重建 CloudPSS skill。

## 核心规则

CloudPSS 仿真、分析类 skill 在完成前，必须命中真实 CloudPSS 环境并得到真实 job/result。

文件驱动类 skill 例如 HDF5 导出、DUDV 绘图，可以不直接访问 CloudPSS，但必须处理真实 CloudPSS 结果格式，并校验输出产物。

只检查 `SIMSTUDIO_TOKEN`、`CLOUDPSS_API_URL` 是否存在的脚本，只能证明环境可能可用，不能证明 skill 可用。

## 合格 Skill 的两层要求

### 1. 仓库结构合格

- `SKILL.md` 存在且 frontmatter 合法。
- `requirements.txt`、`evals/evals.json`、`scripts/verify_<skill>.py`、可选 `mylib/` 符合仓库结构。
- `python -m src.cloudpss_skillrepo validate-skill skills/<skill-id>` 通过。
- `python scripts/check_skill.py <skill-id>` 通过。

### 2. 功能验证合格

- `verify_<skill>.py` 执行 `SKILL.md` 声明的真实 workflow。
- 仿真/分析类 skill 必须调用 CloudPSS SDK 或受控共享包，提交或读取真实 job/result。
- 文件驱动类 skill 必须读取真实结构输入，生成并检查声明的输出文件。
- `SKILL.md`、`evals/evals.json`、验证脚本的字段和产物一致。
- token、url 实际值、`.env` 内容不得进入文档、日志、产物、catalog 或最终回复。

## Maturity 标准

- `draft`：只有设计或文档，没有成功真实验证。
- `experimental`：已有最小真实验证，但场景窄、覆盖不足，或运行时依赖还未稳定治理。
- `validated`：仓库内 `verify_<skill>.py` 可以端到端执行真实 workflow，且观察到的输出与文档一致。
- `published`：在 `validated` 基础上完成维护者 review、catalog 发布准备和依赖版本治理。

如果验证脚本只是 preflight，不允许标为 `validated`。

## 标准开发流程

### 1. 定义可验证目标

不要先写“大而全”的 skill。先把目标收缩为一个可以运行、可以观察结果的任务。

建议模板：

```md
skill 名称：
任务目标：
默认模型或输入夹具：
核心场景：
1.
2.
3.
预期输出：
通过标准：
已知限制：
```

好目标：

> 在 IEEE39 上执行基准潮流，读取母线/线路/发电机结果，再比较负荷提升 20% 后的变化。

坏目标：

> 支持电力系统分析。

如果无法写出明确模型、输入、命令、结果字段和通过标准，就不要开始写 `SKILL.md`。

### 2. 建立真实能力地图

不要只看旧 markdown。必须先看可执行代码、测试和真实示例。

从 `CloudPSS_skillhub` 提取时，至少检查：

- `cloudpss_skills/builtin/<skill>.py`
- `cloudpss_skills_v2/...` 中是否有 v2 实现
- `tests/test_<skill>_unit.py`
- `tests/test_<skill>_integration.py`
- `examples/.../<skill>_example.py`
- `config/<skill>.yaml`
- `docs/skills/<skill>.md`

记录真实运行边界：

- 用到的 CloudPSS SDK API
- 验证使用的模型 RID 或输入文件
- job 类型、轮询行为、timeout
- 读取的 result API 和字段
- 输出文件类型
- 第三方依赖

默认倾向是让每个 skill 相对独立。优先在当前 skill 的 `mylib/` 中实现最小 glue code，并在自己的 `requirements.txt` 中声明依赖；不要为了少量重复代码过早抽共享包。

如果实现依赖 `CloudPSS_skillhub` 或 `psa/` 中的大量 helper，不要把整包复制进 `mylib/`。应优先改写最小独立 runtime；如果仿真分析任务确实很重，例如依赖 `PowerSystemAnalysis`、`SimulationOrchestrator`、批量任务编排、调相机迭代，则把共用逻辑抽成版本化共享包，例如 `psa-runtime` 或 `cloudpss-psa-core`。

### 3. 选择提取策略

#### 策略 A：独立运行时

适用于只需要 `cloudpss` 和少量本地 glue code 的 workflow。

推荐结构：

```text
skills/<skill-id>/
├── SKILL.md
├── requirements.txt
├── evals/evals.json
├── mylib/
│   ├── __init__.py
│   └── runtime.py
└── scripts/
    └── verify_<skill>.py
```

`mylib/runtime.py` 不得 import `CloudPSS_skillhub`、`psa/`、兄弟 skill 或本机绝对路径。

#### 策略 B：共享包

适用于多个 skill 复用同一套 CloudPSS helper，或单个 skill 的真实验证链路过重、不适合在每个 skill 中重复造轮子。

要求：

- 共享逻辑放到独立版本化 Python 包。
- `requirements.txt` 固定到 tag 或 commit。
- `metadata.dependency_strategy` 使用 `shared-package` 或 `hybrid`。
- `metadata.shared_packages` 列出包名。
- 不允许依赖 `main`、`master`、`latest` 等浮动分支。

共享包不是默认选择。只有当复制成本、维护风险或仿真链路复杂度明显高于独立实现时，才使用共享包。

#### 策略 C：文件驱动

仅适用于真实任务就是结果转换、绘图、导出或报告生成的 skill。

验证脚本仍必须做真实工作：

- 读取真实结构输入文件。
- 解析输入。
- 生成声明的输出。
- 检查输出文件存在且结构正确。

文件驱动 skill 可以不访问 CloudPSS live 环境，但输入格式必须来自真实 CloudPSS 输出或明确维护的夹具。


## 凭据处理规则

工作区根目录可能有 `.env`，里面包含 CloudPSS token 和 url。

Agent 可以只为本地验证读取必要值，但禁止：

- 打印 token 值。
- 打印包含敏感信息的完整 url。
- 把凭据写入 `SKILL.md`。
- 把凭据写入 `evals.json`。
- 把凭据写入日志、产物、catalog 或报告。
- 把 `.env` 或 `.cloudpss_token` 复制进 skill 目录。

验证脚本只能输出布尔信息，例如：

```json
{
  "SIMSTUDIO_TOKEN": true,
  "CLOUDPSS_API_URL": true
}
```

如果脚本读取 `.env`，只解析需要的 key，并且只在内存中使用。

## 验证脚本要求

每个非 `draft` skill 必须包含 `scripts/verify_<skill>.py`。

CloudPSS live skill 的验证脚本必须：

1. 安全读取凭据。
2. 配置 CloudPSS SDK。
3. 加载或 fetch 已验证模型。
4. 执行真实仿真或真实分析。
5. 如提交 job，必须轮询到完成、失败或 timeout。
6. 读取真实 result 字段。
7. 断言通过标准。
8. 输出脱敏 JSON 摘要。

摘要可以包含：

- skill id
- 模型 RID
- job id
- final status
- 结果数量
- 关键指标
- 临时产物路径

摘要不得包含：

- token 值
- `.env` 内容
- 大型原始结果 dump
- skill 目录下的 `artifacts/`

验证输出应写到临时目录，或在结束前清理。`scripts/check_skill.py` 会拒绝 skill 目录内的 `artifacts/` 和 `__pycache__/`。

## 最小 Live 验证模式

直接调用 CloudPSS SDK 的 skill 可以参考这个模式：

```python
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from cloudpss import Model, setToken


def load_env_values() -> dict[str, str]:
    values = {}
    for root in [Path.cwd(), *Path(__file__).resolve().parents]:
        env_path = root / ".env"
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        if values:
            break
    return values


def configure_cloudpss() -> None:
    values = load_env_values()
    token = os.environ.get("SIMSTUDIO_TOKEN") or values.get("SIMSTUDIO_TOKEN")
    api_url = os.environ.get("CLOUDPSS_API_URL") or values.get("CLOUDPSS_API_URL")
    if not token:
        raise RuntimeError("SIMSTUDIO_TOKEN is required")
    if api_url:
        os.environ["CLOUDPSS_API_URL"] = api_url
    setToken(token)


def wait_job(job, timeout: int = 300) -> int:
    started = time.time()
    while True:
        status = job.status()
        if status in {1, 2}:
            return status
        if time.time() - started > timeout:
            return -1
        time.sleep(3)


def main() -> None:
    configure_cloudpss()
    model = Model.fetch(os.environ.get("TEST_MODEL_RID", "model/holdme/IEEE3"))

    with tempfile.TemporaryDirectory() as output_dir:
        job = model.runEMT()
        status = wait_job(job)
        if status != 1:
            raise RuntimeError(f"CloudPSS job did not succeed: {status}")

        result = job.result
        plots = result.getPlots()

        print(json.dumps({
            "ok": True,
            "model_rid": getattr(model, "rid", None),
            "job_id": getattr(job, "id", None),
            "status": status,
            "plot_count": len(plots),
            "output_dir": output_dir,
            "token_value_printed": False
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

实际 skill 必须把中间的主体逻辑替换为对应 workflow。不要停留在环境检查。

## `SKILL.md` 写法要求

`SKILL.md` 应在真实验证后编写，而不是先写文档再倒推实现。

必须包含：

- 适用场景
- 前置条件
- 已验证 workflow
- 输出结构
- 限制条件
- 验证入口
- 已验证模型或输入夹具
- 已知失败条件

禁止包含：

- 未验证能力
- 猜测的参数名
- 从旧文档复制但未核实的 API 名
- 没有证据的“全面支持”“通用适配”等表述

frontmatter 必须与真实验证一致：

```yaml
compatibility:
  python: ">=3.11"
  requires_env: true
  required_env_vars:
    - SIMSTUDIO_TOKEN
    - CLOUDPSS_API_URL
metadata:
  owner: cloudpss-team
  category: analysis
  visibility: internal
  maturity: experimental
  entrypoint: scripts/verify_<skill>.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_sdk
```

文件驱动类 skill 可以 `requires_env: false`，但验证脚本必须真实处理夹具并校验输出。

## `evals/evals.json` 写法要求

eval 必须绑定真实验证场景。

推荐结构：

```json
{
  "skill_name": "<skill-id>",
  "evals": [
    {
      "id": 1,
      "name": "verified-live-baseline",
      "goal": "执行已验证 CloudPSS workflow 并汇总结果。",
      "workflow": [
        "加载已验证模型",
        "运行仿真",
        "读取结果",
        "断言摘要字段"
      ],
      "pass_criteria": [
        "verify 脚本退出码为 0",
        "CloudPSS job status 为成功",
        "summary 包含预期结果数量",
        "输出中不包含凭据值"
      ]
    }
  ]
}
```

当前仓库 validator 只要求 `evals` 非空，但 Agent 必须写可测试、可观察的 eval。

## 证据记录

`validated` 或 `published` skill 应在 `SKILL.md` 或 `references/live-verification.md` 中记录脱敏证据。

允许记录：

- 验证日期
- 使用命令
- 模型 RID
- job id
- final status
- 小型结果计数
- 关键指标
- pass/fail 摘要

禁止记录：

- token 值
- `.env` 内容
- 大型 CloudPSS 原始输出
- 生成产物目录
- 一次性调试记录

## 质量门禁

Agent 在宣布 skill 完成前，必须逐项回答“是”：

- 是否检查了真实源码和测试，而不是只看旧文档？
- 是否把 skill 收缩到明确可验证任务？
- 仓库内 verify 脚本是否执行声明的 workflow？
- 如果 skill 使用 CloudPSS 仿真，是否提交或读取了真实 CloudPSS job/result？
- 如果 skill 是文件驱动，是否转换了真实结构夹具并检查输出？
- `SKILL.md` 是否只描述已验证行为？
- `evals.json` 是否与 verify 脚本和输出一致？
- 依赖是否明确且最小？
- 共享代码是否要么是极小本地 `mylib/`，要么是固定版本共享包？
- skill 目录中是否没有 `.env`、`.cloudpss_token`、`artifacts/`、`__pycache__/`？
- `python scripts/check_skill.py <skill-id>` 是否通过？
- `python -m src.cloudpss_skillrepo release-check` 是否通过？

任一项为否，skill 就没有完成。

## Agent 反模式

不要这样做：

- 先写 `SKILL.md`，再倒推脚本。
- 用环境变量 preflight 作为唯一验证。
- 把旧项目整包复制进 `mylib/`。
- 从新 skill import `CloudPSS_skillhub`。
- 把探索过程笔记留在 skill 目录。
- 声称支持未验证模型、故障类型或结果格式。
- live 验证失败后，只靠 `experimental` 标签包装成可用 skill。

## 推荐创建清单

每个 CloudPSS skill 按这个顺序创建：

1. 定义任务目标和通过标准。
2. 检查真实代码、测试、示例、配置。
3. 选择独立运行时、共享包或文件驱动策略。
4. 实现最小真实 runtime。
5. 运行真实 CloudPSS 验证或真实结构夹具转换。
6. 记录脱敏证据。
7. 根据已验证 workflow 写 `SKILL.md`。
8. 根据同一场景写 `evals/evals.json`。
9. 运行仓库校验。
10. 清理生成产物和临时文件。

结构检查是最后一道门，不是 skill 成功的定义。
