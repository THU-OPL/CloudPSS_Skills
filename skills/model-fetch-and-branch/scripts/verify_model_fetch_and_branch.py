from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_READONLY_MODEL_RID, configure_token, create_local_branch, load_model_from_source, search_models, summarize_model


def main() -> None:
    configure_token()
    model = load_model_from_source(DEFAULT_READONLY_MODEL_RID)
    branch_path = str(SKILL_DIR / "artifacts" / "model-fetch-working-copy.yaml")
    Path(branch_path).parent.mkdir(parents=True, exist_ok=True)
    result = {
        "ok": True,
        "model": summarize_model(model),
        "search_preview": search_models("IEEE", page_size=3),
        "local_branch": create_local_branch(model, branch_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
