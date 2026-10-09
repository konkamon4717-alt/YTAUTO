"""เก็บประวัติเรื่องที่เคยทำ เพื่อไม่ให้ AI คิดพล็อตซ้ำ (แยกไฟล์ต่อช่อง)"""
import json
import pathlib
from datetime import datetime, timezone

from . import config


def _history() -> "pathlib.Path":
    return config.data_dir() / "history.json"


def _empty() -> dict:
    return {"published": [], "premises": []}


def load() -> dict:
    history = _history()
    if not history.exists():
        return _empty()
    try:
        data = json.loads(history.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # ไฟล์พังไม่ควรทำให้ทั้งระบบหยุด — เริ่มใหม่ดีกว่าค้าง
        return _empty()
    data.setdefault("published", [])
    data.setdefault("premises", [])
    return data


def save(data: dict) -> None:
    history = _history()
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def recent_premises(limit: int = 120) -> list[str]:
    return load()["premises"][-limit:]


def record(premise: str, video: dict) -> None:
    data = load()
    data["premises"].append(premise)
    data["published"].append(
        {**video, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    )
    data["premises"] = data["premises"][-500:]
    data["published"] = data["published"][-300:]
    save(data)
