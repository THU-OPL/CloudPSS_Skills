---
name: model-fetch-and-branch
description: 使用 CloudPSS SDK 获取模型、搜索可访问算例，并创建本地研究分支副本。当用户提到获取算例、搜索模型、创建本地工作副本或研究分支管理时使用。
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: false
  required_env_vars: []
  notes: Requires a valid .cloudpss_token file in the working directory.
metadata:
  owner: cloudpss-team
  category: workflow
  visibility: internal
  maturity: validated
  entrypoint: scripts/verify_model_fetch_and_branch.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: direct_cloudpss_sdk
---

# Model Fetch And Branch

## When to use

- 需要从 CloudPSS 获取一个已有算例
- 需要搜索可访问的模型
- 需要创建本地研究副本，避免直接污染原始模型

## Workflow

1. 读取 `.cloudpss_token`
2. 使用 `Model.fetch()` 或 `Model.load()` 获取模型
3. 可选使用 `Model.fetchMany()` 搜索候选模型
4. 使用 `Model.dump()` 创建本地工作副本
5. 重新加载副本并输出摘要

## Output

- 模型基础摘要
- 搜索结果摘要
- 本地研究副本路径

## Constraints

- 默认依赖 `.cloudpss_token`
- 主要覆盖“取模型 + 建本地分支”工作流
- 不负责复杂仿真分析
