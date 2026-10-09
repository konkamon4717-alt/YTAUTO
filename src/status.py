"""เขียนสถานะลง docs/<ช่อง>/status.json ให้ห้องควบคุมอ่าน"""
import json
from datetime import datetime, timezone

from . import config


def _status():
    return config.docs_dir() / "status.json"


MAX_RUNS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict:
    status = _status()
    if not status.exists():
        return {"updated_at": None, "runs": []}
    try:
        return json.loads(status.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated_at": None, "runs": []}


def record_run(entry: dict) -> None:
    data = load()
    data["updated_at"] = _now()
    data["runs"] = ([{**entry, "at": _now()}] + data.get("runs", []))[:MAX_RUNS]
    status = _status()
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
