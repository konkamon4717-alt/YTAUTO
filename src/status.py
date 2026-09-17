"""เขียนสถานะลง docs/status.json ให้หน้า dashboard อ่าน"""
import json
from datetime import datetime, timezone

from .config import ROOT

STATUS = ROOT / "docs" / "status.json"
MAX_RUNS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict:
    if not STATUS.exists():
        return {"updated_at": None, "runs": []}
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated_at": None, "runs": []}


def record_run(entry: dict) -> None:
    data = load()
    data["updated_at"] = _now()
    data["runs"] = ([{**entry, "at": _now()}] + data.get("runs", []))[:MAX_RUNS]
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
