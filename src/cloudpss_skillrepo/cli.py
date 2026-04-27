from __future__ import annotations

import argparse
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"
CATALOG_PATH = ROOT / "catalog" / "skills-index.json"
DIST_DIR = ROOT / "dist"
CATEGORIES = {"workflow", "analysis", "export", "inspection", "utility"}
VISIBILITIES = {"internal", "team", "public"}
MATURITIES = {"draft", "experimental", "validated", "published"}
DEPENDENCY_STRATEGIES = {"bundled-mylib", "shared-package", "hybrid"}


@dataclass
class ValidationIssue:
    level: str
    message: str


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml_safe_load(load_text(path))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return data


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(load_text(path))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def parse_frontmatter(skill_md: Path) -> dict[str, Any]:
    text = load_text(skill_md)
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md missing YAML frontmatter")
    data = yaml_safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML object")
    return data


def extract_markdown_title(skill_md: Path) -> str:
    text = load_text(skill_md)
    text = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.DOTALL)
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return skill_md.parent.name.replace("-", " ").title()


def parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def simple_yaml_load(text: str) -> Any:
    lines = [line.rstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    index = 0

    def parse_block(indent: int) -> Any:
        nonlocal index
        mapping: dict[str, Any] = {}
        sequence: list[Any] | None = None

        while index < len(lines):
            line = lines[index]
            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected indentation: {line}")

            stripped = line.strip()
            if stripped.startswith("- "):
                if mapping:
                    raise ValueError("Cannot mix mapping and sequence at same indentation level")
                if sequence is None:
                    sequence = []
                item_value = stripped[2:].strip()
                index += 1
                if item_value:
                    sequence.append(parse_scalar(item_value))
                else:
                    sequence.append(parse_block(indent + 2))
                continue

            if sequence is not None:
                raise ValueError("Cannot mix sequence and mapping at same indentation level")

            if ":" not in stripped:
                raise ValueError(f"Invalid YAML line: {line}")
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            index += 1
            if raw_value:
                mapping[key] = parse_scalar(raw_value)
            else:
                if index < len(lines):
                    next_line = lines[index]
                    next_indent = len(next_line) - len(next_line.lstrip(" "))
                    if next_indent <= indent:
                        mapping[key] = {}
                    else:
                        mapping[key] = parse_block(indent + 2)
                else:
                    mapping[key] = {}

        return sequence if sequence is not None else mapping

    return parse_block(0)


def yaml_safe_load(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text)
    return simple_yaml_load(text)


def looks_like_vcs_requirement(line: str) -> bool:
    return "git+" in line or "github.com/" in line


def is_immutable_vcs_requirement(line: str) -> bool:
    if "@git+" in line:
        ref = line.rsplit("@", 1)[-1]
    elif "git+" in line and "@" in line:
        ref = line.rsplit("@", 1)[-1]
    else:
        return False
    ref = ref.strip()
    if not ref:
        return False
    if ref.lower() in {"main", "master", "head", "latest"}:
        return False
    return True


def validate_skill_dir(skill_dir: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    skill_md = skill_dir / "SKILL.md"
    evals = skill_dir / "evals" / "evals.json"
    requirements = skill_dir / "requirements.txt"
    mylib_dir = skill_dir / "mylib"
    scripts_dir = skill_dir / "scripts"

    if not skill_md.exists():
        issues.append(ValidationIssue("error", "Missing SKILL.md"))
        return issues
    if not evals.exists():
        issues.append(ValidationIssue("error", "Missing evals/evals.json"))
    if not requirements.exists():
        issues.append(ValidationIssue("error", "Missing requirements.txt"))
    if not scripts_dir.exists():
        issues.append(ValidationIssue("error", "Missing scripts/ directory"))

    try:
        frontmatter = parse_frontmatter(skill_md)
    except Exception as exc:
        issues.append(ValidationIssue("error", f"Invalid SKILL.md frontmatter: {exc}"))
        return issues

    try:
        evals_data = load_json(evals)
    except Exception as exc:
        issues.append(ValidationIssue("error", f"Invalid evals/evals.json: {exc}"))
        return issues

    dir_name = skill_dir.name
    front_name = frontmatter.get("name")
    eval_skill_name = evals_data.get("skill_name")

    if front_name != dir_name:
        issues.append(ValidationIssue("error", f"Frontmatter name '{front_name}' does not match directory '{dir_name}'"))
    if eval_skill_name != dir_name:
        issues.append(ValidationIssue("error", f"Evals skill_name '{eval_skill_name}' does not match directory '{dir_name}'"))

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(ValidationIssue("error", "SKILL.md description must be a non-empty string"))

    compatibility = frontmatter.get("compatibility", {})
    if compatibility and not isinstance(compatibility, dict):
        issues.append(ValidationIssue("error", "SKILL.md compatibility must be a YAML object"))
        compatibility = {}

    metadata = frontmatter.get("metadata", {})
    if not isinstance(metadata, dict):
        issues.append(ValidationIssue("error", "SKILL.md metadata must be a YAML object"))
        metadata = {}

    owner = metadata.get("owner")
    category = metadata.get("category")
    visibility = metadata.get("visibility")
    maturity = metadata.get("maturity")
    entrypoint = metadata.get("entrypoint")
    dependency_strategy = metadata.get("dependency_strategy")
    shared_packages = metadata.get("shared_packages", [])
    verification_method = metadata.get("verification_method")

    if not isinstance(owner, str) or not owner.strip():
        issues.append(ValidationIssue("error", "SKILL.md metadata.owner must be a non-empty string"))
    if category not in CATEGORIES:
        issues.append(
            ValidationIssue(
                "error",
                f"SKILL.md metadata.category must be one of: {', '.join(sorted(CATEGORIES))}",
            )
        )
    if visibility not in VISIBILITIES:
        issues.append(
            ValidationIssue(
                "error",
                f"SKILL.md metadata.visibility must be one of: {', '.join(sorted(VISIBILITIES))}",
            )
        )
    if maturity not in MATURITIES:
        issues.append(
            ValidationIssue(
                "error",
                f"SKILL.md metadata.maturity must be one of: {', '.join(sorted(MATURITIES))}",
            )
        )
    if dependency_strategy not in DEPENDENCY_STRATEGIES:
        issues.append(
            ValidationIssue(
                "error",
                "SKILL.md metadata.dependency_strategy must be one of bundled-mylib, shared-package, hybrid",
            )
        )
    if not isinstance(shared_packages, list):
        issues.append(ValidationIssue("error", "SKILL.md metadata.shared_packages must be a list"))
    if not isinstance(entrypoint, str) or not entrypoint.startswith("scripts/"):
        issues.append(ValidationIssue("error", "SKILL.md metadata.entrypoint must point to scripts/..."))
    elif not (skill_dir / entrypoint).exists():
        issues.append(ValidationIssue("error", f"Entrypoint script not found: {entrypoint}"))

    if dependency_strategy in {"bundled-mylib", "hybrid"} and not mylib_dir.exists():
        issues.append(
            ValidationIssue(
                "error",
                "Dependency strategy requires a local mylib/ directory but none was found",
            )
        )
    if dependency_strategy == "shared-package" and mylib_dir.exists():
        issues.append(
            ValidationIssue(
                "warning",
                "dependency_strategy is 'shared-package' but mylib/ is present; use 'hybrid' if both are intended",
            )
        )
    if dependency_strategy in {"shared-package", "hybrid"} and not shared_packages:
        issues.append(
            ValidationIssue(
                "error",
                "Dependency strategy requires metadata.shared_packages to list the shared package names",
            )
        )

    direct_files = list(scripts_dir.glob("verify_*.py"))
    if not direct_files:
        issues.append(ValidationIssue("error", "Missing scripts/verify_<skill>.py validation script"))
    if not isinstance(verification_method, str) or not verification_method.strip():
        issues.append(ValidationIssue("error", "SKILL.md metadata.verification_method must be a non-empty string"))

    eval_items = evals_data.get("evals")
    if not isinstance(eval_items, list) or not eval_items:
        issues.append(ValidationIssue("error", "evals/evals.json must contain a non-empty evals list"))

    if requirements.exists():
        requirement_lines = [
            line.strip()
            for line in load_text(requirements).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not requirement_lines:
            issues.append(ValidationIssue("error", "requirements.txt must contain at least one dependency"))
        for line in requirement_lines:
            if looks_like_vcs_requirement(line) and not is_immutable_vcs_requirement(line):
                issues.append(
                    ValidationIssue(
                        "error",
                        "VCS dependency must pin an immutable Git ref or version tag, not a floating branch: "
                        f"{line}",
                    )
                )
        normalized_lines = [line.lower() for line in requirement_lines]
        for package_name in shared_packages if isinstance(shared_packages, list) else []:
            normalized_package = str(package_name).lower()
            if not any(line.startswith(normalized_package) for line in normalized_lines):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Shared package '{package_name}' is listed in metadata.shared_packages but not found in requirements.txt",
                    )
                )

    mylib_files = list(mylib_dir.rglob("*.py")) if mylib_dir.exists() else []
    if mylib_dir.exists() and dependency_strategy in {"bundled-mylib", "hybrid"} and not mylib_files:
        issues.append(ValidationIssue("warning", "mylib/ exists but contains no Python files"))

    return issues


def build_catalog() -> dict[str, Any]:
    skills: list[dict[str, Any]] = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        frontmatter = parse_frontmatter(skill_dir / "SKILL.md")
        metadata = frontmatter.get("metadata", {})
        skills.append(
            {
                "id": frontmatter["name"],
                "title": extract_markdown_title(skill_dir / "SKILL.md"),
                "summary": frontmatter["description"],
                "category": metadata["category"],
                "visibility": metadata["visibility"],
                "maturity": metadata["maturity"],
                "owner": metadata["owner"],
                "entrypoint": metadata["entrypoint"],
                "dependency_strategy": metadata["dependency_strategy"],
                "shared_packages": metadata.get("shared_packages", []),
                "description": frontmatter["description"]
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skills": skills,
    }


def command_validate_skill(args: argparse.Namespace) -> int:
    skill_dir = (ROOT / args.path).resolve() if not Path(args.path).is_absolute() else Path(args.path)
    issues = validate_skill_dir(skill_dir)
    payload = {
        "skill": str(skill_dir),
        "ok": not any(issue.level == "error" for issue in issues),
        "issues": [issue.__dict__ for issue in issues],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def package_skill(skill_dir: Path, output_dir: Path) -> Path:
    archive_path = output_dir / f"{skill_dir.name}.skill"
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, arcname=str(Path(skill_dir.name) / path.relative_to(skill_dir)))
    return archive_path


def command_package_skill(args: argparse.Namespace) -> int:
    skill_dir = (ROOT / args.path).resolve() if not Path(args.path).is_absolute() else Path(args.path)
    output_dir = (
        (ROOT / args.output).resolve()
        if args.output and not Path(args.output).is_absolute()
        else Path(args.output).resolve()
        if args.output
        else DIST_DIR
    )
    issues = validate_skill_dir(skill_dir)
    payload = {
        "skill": str(skill_dir),
        "ok": not any(issue.level == "error" for issue in issues),
        "issues": [issue.__dict__ for issue in issues],
    }
    if not payload["ok"]:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    archive_path = package_skill(skill_dir, output_dir)
    payload["archive"] = str(archive_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_index_skills(args: argparse.Namespace) -> int:
    catalog = build_catalog()
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "catalog": str(CATALOG_PATH), "skill_count": len(catalog["skills"])}, ensure_ascii=False, indent=2))
    return 0


def command_release_check(args: argparse.Namespace) -> int:
    all_issues: dict[str, Any] = {}
    ok = True
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        issues = validate_skill_dir(skill_dir)
        all_issues[skill_dir.name] = [issue.__dict__ for issue in issues]
        if any(issue.level == "error" for issue in issues):
            ok = False
    print(json.dumps({"ok": ok, "skills": all_issues}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def command_list_skills(args: argparse.Namespace) -> int:
    rows = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        frontmatter = parse_frontmatter(skill_dir / "SKILL.md")
        metadata = frontmatter.get("metadata", {})
        rows.append(
            {
                "id": frontmatter["name"],
                "maturity": metadata["maturity"],
                "category": metadata["category"],
                "entrypoint": metadata["entrypoint"],
            }
        )
    print(json.dumps({"skills": rows}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloudpss-skillrepo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-skill")
    validate_parser.add_argument("path")
    validate_parser.set_defaults(func=command_validate_skill)

    package_parser = subparsers.add_parser("package-skill")
    package_parser.add_argument("path")
    package_parser.add_argument("output", nargs="?")
    package_parser.set_defaults(func=command_package_skill)

    index_parser = subparsers.add_parser("index-skills")
    index_parser.set_defaults(func=command_index_skills)

    release_parser = subparsers.add_parser("release-check")
    release_parser.set_defaults(func=command_release_check)

    list_parser = subparsers.add_parser("list-skills")
    list_parser.set_defaults(func=command_list_skills)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)
