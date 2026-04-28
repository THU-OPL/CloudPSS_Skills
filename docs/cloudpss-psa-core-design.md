# cloudpss-psa-core Design

## Goals

`cloudpss-psa-core` is the shared private Python package for CloudPSS team skills that need reusable PSA-oriented capabilities.

It exists to solve these problems:

- avoid copying large PSA helper code into every skill
- provide a stable compatibility layer over the CloudPSS SDK
- give multiple skills a common token, model, job, and result utility layer
- version shared logic independently from the skill repository

## What Belongs in the Shared Package

Good candidates for `cloudpss-psa-core`:

- token loading and CloudPSS SDK configuration
- model loading and fetch-or-load helpers
- job polling and timeout handling
- common result-table normalization
- common model summary helpers
- stable wrappers for repeated PSA workflows

Bad candidates:

- one-off study parameters for a single skill
- domain prompts or skill-facing instructions
- skill-specific report formatting
- scenario constants that are only valid for one benchmark model

## Repository Structure

Current repository structure:

```text
cloudpss-psa-core/
├─ src/psa/
│  ├─ tool_box/
│  └─ utils/
├─ tests/
│  ├─ test_tables.py
│  └─ test_metadata.py
├─ pyproject.toml
├─ README.md
└─ LICENSE
```

## Version Strategy

Use semantic versioning:

- `MAJOR`: breaking API or behavior changes that require skill updates
- `MINOR`: backward-compatible new helpers or wrappers
- `PATCH`: bug fixes, table parsing fixes, timeout fixes, doc fixes

Recommended release policy:

- skills in `published` state should pin to a tag, e.g. `v0.3.1`
- internal experiments may pin to a commit hash
- do not pin published skills to floating branches

## Integration Contract for Skills

Skills should integrate in one of two ways:

### shared-package

Use when all reusable private logic can come from the package.

- `requirements.txt` includes `cloudpss-psa-core @ git+...@vX.Y.Z`
- `mylib/` is omitted
- `SKILL.md` sets `dependency_strategy: shared-package`

### hybrid

Use when the skill needs both shared reusable PSA logic and local study-specific glue.

- `requirements.txt` includes `cloudpss-psa-core @ git+...@vX.Y.Z`
- `mylib/` contains only skill-specific scenario code
- `SKILL.md` sets `dependency_strategy: hybrid`

## Runtime Surface

The shared package now standardizes on the packaged `psa.*` runtime boundary:

- `psa.tool_box.PowerSystemAnalysis`
- `psa.tool_box.CaseEditToolbox`
- `psa.utils.*`

Skills should depend on the GitHub package and import from `psa.*`, rather than copying PSA runtime code into a skill-local directory.

## Risks

- if too much model-specific study logic moves into the shared package, the package becomes a second monolith
- if package APIs are too low-level, skills still duplicate wrapper code
- if published skills pin only to commits, maintainers lose release clarity

## Decision

Use `cloudpss-psa-core` as the versioned PSA runtime package for skills, not as a place for one-off skill logic.
