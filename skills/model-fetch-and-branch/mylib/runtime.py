from __future__ import annotations

from pathlib import Path

from cloudpss import Model, setToken


DEFAULT_READONLY_MODEL_RID = "model/CloudPSS/IEEE39"


def load_token(token_path: str = ".cloudpss_token") -> str:
    path = Path(token_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing token file: {path}")
    return path.read_text(encoding="utf-8").strip()


def configure_token(token_path: str = ".cloudpss_token") -> str:
    token = load_token(token_path)
    setToken(token)
    return token


def load_model_from_source(source: str):
    candidate = Path(source).expanduser()
    if candidate.exists():
        return Model.load(str(candidate))
    return Model.fetch(source)


def summarize_model(model) -> dict:
    return {
        "name": getattr(model, "name", ""),
        "rid": getattr(model, "rid", ""),
        "job_count": len(getattr(model, "jobs", [])),
        "config_count": len(getattr(model, "configs", [])),
        "component_count": len(model.getAllComponents()),
    }


def search_models(keyword: str = "IEEE", page_size: int = 5) -> list[dict]:
    return Model.fetchMany(name=keyword, pageSize=page_size)


def create_local_branch(model, output_path: str) -> dict:
    Model.dump(model, output_path, compress=None)
    reloaded = Model.load(output_path)
    return {
        "path": output_path,
        "summary": summarize_model(reloaded),
    }
