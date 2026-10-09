"""บอกว่ามีช่องอะไรบ้างและช่องไหนเปิดใช้งานอยู่

  python -m src.channels            รายชื่อช่องที่เปิดอยู่ (JSON ให้ GitHub Actions ใช้ทำ matrix)
  python -m src.channels --all      ทุกช่องพร้อมสถานะ ไว้ดูด้วยตา
  python -m src.channels --manifest เขียน docs/channels.json ให้ห้องควบคุมอ่าน

ช่องที่ยังตั้ง secret ไม่ครบต้องปิดไว้ก่อน ไม่งั้นรอบประจำวันจะล้มทุกวัน
แล้วความล้มเหลวจริง ๆ จะจมหายไปในกองการแจ้งเตือนที่เรารู้อยู่แล้วว่าจะล้ม
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from . import config


def info(name: str) -> dict:
    config.use(name)
    cfg = config.load()
    return {
        "key": name,
        "title": cfg["channel"]["name"],
        "enabled": bool((cfg.get("run") or {}).get("enabled", True)),
        "per_day": (cfg.get("run") or {}).get("per_day", 1),
        "animated": bool((cfg.get("animation") or {}).get("enabled")),
        "images": (cfg.get("images") or {}).get("source", "generate"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="แสดงทุกช่องพร้อมสถานะ")
    parser.add_argument("--manifest", action="store_true",
                        help="เขียน docs/channels.json ให้ห้องควบคุมอ่าน")
    args = parser.parse_args(argv)

    rows = [info(name) for name in config.available()]

    if args.manifest:
        out = config.ROOT / "docs" / "channels.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "channels": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"เขียน {out} แล้ว ({len(rows)} ช่อง)")
        return 0

    if args.all:
        for r in rows:
            mark = "เปิด" if r["enabled"] else "ปิด "
            print(f"  [{mark}] {r['key']:<10} {r['title']:<16} "
                  f"ภาพ:{r['images']:<9} ขยับ:{'ใช่' if r['animated'] else 'ไม่'}")
        return 0

    # ค่าเริ่มต้นออกมาเป็น JSON ล้วน เพราะ GitHub Actions เอาไปทำ matrix ตรง ๆ
    print(json.dumps([r["key"] for r in rows if r["enabled"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
