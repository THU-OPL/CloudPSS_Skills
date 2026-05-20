from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import MODEL_ID, run_maintenance_security_analysis  # noqa: E402


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else MODEL_ID
    result = run_maintenance_security_analysis(model_id=source)
    if result["candidate_line_count"] <= 1:
        raise RuntimeError("Not enough AC lines for maintenance plus residual N-1 screening")
    if not result["maintenance_case"]["summary"]:
        raise RuntimeError("Maintenance case summary is empty")
    if result["residual_screened_line_count"] <= 0:
        raise RuntimeError("No residual contingencies were screened")
    if not result["residual_severity_ranking"]:
        raise RuntimeError("Residual severity ranking is empty")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
