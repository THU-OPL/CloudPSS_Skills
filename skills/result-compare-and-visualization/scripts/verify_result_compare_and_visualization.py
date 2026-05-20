from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_live_comparison  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "result-compare-and-visualization"
    result = run_live_comparison(model, output_dir)
    if len(result["job_ids"]) < 2:
        raise RuntimeError("Expected at least two live EMT jobs")
    if not result["comparison"]["comparison"]:
        raise RuntimeError("Comparison is empty")
    for path in [result["artifacts"]["json_path"], result["artifacts"]["markdown_path"], *result["artifacts"]["charts"]]:
        artifact = Path(path)
        if not artifact.exists() or artifact.stat().st_size <= 0:
            raise RuntimeError(f"Artifact missing or empty: {artifact}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
