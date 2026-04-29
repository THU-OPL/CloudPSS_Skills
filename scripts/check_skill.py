from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_FILES = [".env", ".cloudpss_token"]
GENERATED_DIRS = ["artifacts", "__pycache__"]
NESTED_SENTINELS = ["SKILL.md", "requirements.txt", "evals", "mylib", "scripts"]


def run_command(args: list[str]) -> None:
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def check_layout(skill_dir: Path, skill_id: str) -> None:
    missing = []
    for relative in ["SKILL.md"]:
        if not (skill_dir / relative).exists():
            missing.append(relative)

    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Skill '{skill_id}' is missing required paths: {joined}. "
            "Expected layout: skills/<skill-id>/SKILL.md"
        )

    nested_dir = skill_dir / skill_id
    if nested_dir.is_dir() and any((nested_dir / name).exists() for name in NESTED_SENTINELS):
        raise SystemExit(
            f"Skill '{skill_id}' appears to be nested one level too deep: found {nested_dir}. "
            "Move its contents directly under skills/<skill-id>/."
        )


def check_sensitive_outputs(skill_dir: Path, skill_id: str) -> None:
    problems: list[str] = []
    for name in SENSITIVE_FILES:
        path = skill_dir / name
        if path.exists():
            problems.append(str(path.relative_to(ROOT)))

    for name in GENERATED_DIRS:
        path = skill_dir / name
        if path.exists():
            problems.append(str(path.relative_to(ROOT)))

    for path in skill_dir.rglob("__pycache__"):
        if path.is_dir():
            problems.append(str(path.relative_to(ROOT)))

    if problems:
        joined = "\n".join(f"- {item}" for item in sorted(set(problems)))
        raise SystemExit(
            "Remove sensitive or generated files before submitting:\n"
            f"{joined}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local pre-submit checks for one skill.")
    parser.add_argument("skill_id", help="Skill directory name under skills/")
    parser.add_argument(
        "--skip-release-check",
        action="store_true",
        help="Skip repository-wide release-check.",
    )
    args = parser.parse_args()

    skill_dir = ROOT / "skills" / args.skill_id
    if not skill_dir.is_dir():
        raise SystemExit(f"Skill directory not found: {skill_dir}")

    print(f"[check-skill] Checking layout for skills/{args.skill_id}")
    check_layout(skill_dir, args.skill_id)

    print(f"[check-skill] Checking sensitive/generated files for skills/{args.skill_id}")
    check_sensitive_outputs(skill_dir, args.skill_id)

    print(f"[check-skill] Running validate-skill for skills/{args.skill_id}")
    run_command([sys.executable, "-m", "src.cloudpss_skillrepo", "validate-skill", f"skills/{args.skill_id}"])

    if not args.skip_release_check:
        print("[check-skill] Running repository-wide release-check")
        run_command([sys.executable, "-m", "src.cloudpss_skillrepo", "release-check"])

    print("[check-skill] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
