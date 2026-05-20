from __future__ import annotations

import json
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from mylib.runtime import DEFAULT_MODEL_RID, configure_token, load_model_from_source, run_emt_and_export_waveforms  # noqa: E402


def main() -> None:
    configure_token()
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_RID
    model = load_model_from_source(source)
    root = SKILL_DIR.parents[1]
    output_dir = root / "results" / "skill-verification" / "waveform-export"
    result = run_emt_and_export_waveforms(model, output_dir)
    export = result["export"]
    if export["exported_channel_count"] <= 0:
        raise RuntimeError("No channels exported")
    for path in [export["json_path"], *export["csv_paths"]]:
        artifact = Path(path)
        if not artifact.exists() or artifact.stat().st_size <= 0:
            raise RuntimeError(f"Export artifact missing or empty: {artifact}")
    print(json.dumps({"ok": True, "source": source, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
