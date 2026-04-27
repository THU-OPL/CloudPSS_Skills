# Claude Code Alignment

## 1. Reference Basis

This repository is aligned to the public Claude Code / Anthropic Skills model in these areas:

- a skill is a directory, not a single file
- `SKILL.md` is the primary model-facing contract
- skill loading is progressive: metadata -> `SKILL.md` -> scripts/resources when needed
- scripts are allowed and are the preferred place for deterministic work

Public references reviewed on April 27, 2026:

- Claude Code skills documentation: https://docs.claude.com/en/docs/claude-code/skills
- Anthropic public skills repository: https://github.com/anthropics/skills
- Agent Skills script guidance: https://agentskills.io/skill-creation/using-scripts

## 2. Where CloudPSS Is Stricter

CloudPSS adds repository governance constraints that are stricter than the public examples:

- every skill must remain usable after `CloudPSS_skillhub/` and `psa/` are deleted
- every skill must declare third-party Python dependencies in its own `requirements.txt`
- every skill must vendor only its own minimal private helper code in `mylib/`
- large private logic shared by multiple skills should be published as an independently versioned package
- skills may not import sibling skills or repository-external private modules
- MCP-based runtime assumptions are intentionally excluded in this version

## 3. Dependency Strategy

Claude / Anthropic skills commonly rely on bundled scripts plus runtime-specific dependency handling.
For CloudPSS, the dependency rule is made explicit and local:

- model-facing trigger and workflow live in `SKILL.md`
- lightweight governance metadata also lives in `SKILL.md` frontmatter
- Python package dependencies live in `requirements.txt`
- private skill-local glue code lives in `mylib/`
- cross-skill private reusable code should live in a separately versioned package
- executable and verification scripts live in `scripts/`

This split prevents hidden dependencies and keeps each skill portable as a standalone asset.

## 4. Why `mylib/` Exists

Public skill examples often keep helper logic inside scripts when the scope is small.
CloudPSS needs a stronger maintainability boundary because some skills will encapsulate domain logic:

- `scripts/` should stay thin and task-oriented
- `mylib/` should hold the minimum reusable private code needed by that skill only
- code shared by many skills should not be copy-pasted into every `mylib/`
- `mylib/` is not a shared SDK layer and must not become a backdoor replacement for `psa/`

## 5. Governance Difference

Claude-style skills optimize for model usability first.
This repository adds a second governance plane for maintainers:

- `validate-skill` checks required structure and metadata consistency
- `package-skill` emits a portable `.skill` archive
- `index-skills` rebuilds the repository catalog
- `release-check` evaluates whether all included skills satisfy release gates

That separation is intentional:

- `SKILL.md` remains the single human-authored metadata file
- maintainers can enforce quality without weakening skill portability
