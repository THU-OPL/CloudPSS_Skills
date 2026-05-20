from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_EMT_MODEL_RID, configure_token, load_model_from_source, run_emt_workflow


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    export_dir = root / "results" / "skill-verification" / "emt-simulation-workflow"
    result = {
        "ok": True,
        "source": source,
        "model_name": getattr(model, "name", ""),
        "model_rid": getattr(model, "rid", ""),
        "simulation": run_emt_workflow(model, timeout=300, export_dir=export_dir),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
