from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_SOURCE, configure_token, load_model_from_source, run_fault_study


def main() -> None:
    configure_token()
    model = load_model_from_source(DEFAULT_MODEL_SOURCE)
    result = {
        "ok": True,
        "source": DEFAULT_MODEL_SOURCE,
        "study_results": run_fault_study(model),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
