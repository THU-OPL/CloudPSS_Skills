---
name: example-skill
description: Briefly explain what this skill does and when it should trigger.
license: Internal Use Only
compatibility:
  python: ">=3.11"
  requires_env: false
  required_env_vars: []
  notes: If you depend on a shared private package, pin it to an immutable Git tag or commit in requirements.txt.
metadata:
  owner: team-name
  category: workflow
  visibility: internal
  maturity: draft
  entrypoint: scripts/verify_example_skill.py
  dependency_strategy: bundled-mylib
  shared_packages: []
  verification_method: manual
---

# Example Skill

## When to use

- Describe the user situations where this skill should be used.

## Workflow

1. Describe the validated workflow.

## Output

- Describe the final result shape.

## Constraints

- Describe the important verified limits.
