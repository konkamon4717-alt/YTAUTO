"""ตรวจสุขภาพทุกบริการที่ระบบพึ่งพา

รันทุกเช้าก่อนรอบผลิตจริง เพื่อให้รู้ว่าอะไรกำลังจะพัง **ก่อน** ที่คลิปจะหายไปหลายวัน
แล้วเราเพิ่งมาสังเกตทีหลัง

ทุกการตรวจต้อง "ถูกและเบา" — ห้ามเผาโควต้าที่ต้องเอาไปใช้ผลิตจริง
เช่นเช็ค YouTube ด้วย channels.list ที่กิน 1 หน่วยจาก 10,000 ไม่ใช่ลองอัปโหลดจริง

  python -m src.health
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config




def _check(name: str, essential: bool, fn) -> dict:
    started = time.time()
    try:
        detail = fn() or ""
        return {"name": name, "ok": True, "essential": essential,
                "detail": str(detail)[:200], "ms": round((time.time() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001 - ทุกความล้มเหลวคือผลการตรวจ ไม่ใช่ข้อยกเว้น
        return {"name": name, "ok": False, "essential": essential,
                "detail": f"{type(exc).__name__}: {exc}"[:200],
                "ms": round((time.time() - started) * 1000)}


# ---------- ตัวตรวจแต่ละบริการ ----------

def check_gemini(cfg: dict) -> str:
    import requests
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": config.secret("GEMINI_API_KEY")},
                     timeout=45)
    r.raise_for_status()
    names = {m["name"].replace("models/", "") for m in r.json().get("models", [])}
    # config เปลี่ยนจาก model เดี่ยวเป็น models หลายรุ่นตอนแก้ปัญหา 503
    # ตัวตรวจนี้ยังอ่านคีย์เก่าอยู่จนพัง — ต้องยอมรับทั้งสองแบบ
    wanted = cfg["llm"].get("models") or [cfg["llm"].get("model")]
    usable = [m for m in wanted if m in names]
    if not usable:
        raise RuntimeError(f"ไม่พบรุ่นที่ตั้งไว้เลย: {', '.join(filter(None, wanted))}")
    return f"ใช้ได้ {len(usable)}/{len(wanted)} รุ่น | ตัวแรก {usable[0]}"


def check_pollinations(cfg: dict) -> str:
    import requests
    r = requests.get("https://gen.pollinations.ai/models", timeout=45)
    r.raise_for_status()
    names = {m["name"] for m in r.json()}
    missing = [m for m in cfg["images"]["models"]
               if m not in names and "/" in m]
    if missing:
        raise RuntimeError(f"โมเดลภาพหายไปจากรายการ: {', '.join(missing)}")
    return f"{len(names)} โมเดล | รุ่นภาพที่ตั้งไว้ยังอยู่ครบ"


def check_edge_tts(cfg: dict) -> str:
    import asyncio

    import edge_tts

    async def probe():
        voices = await edge_tts.list_voices()
        return [v["ShortName"] for v in voices]

    names = asyncio.run(probe())
    if cfg["tts"]["voice"] not in names:
        raise RuntimeError(f"ไม่พบเสียง {cfg['tts']['voice']}")
    return f"{cfg['tts']['voice']} พร้อมใช้"


def check_huggingface(cfg: dict) -> str:
    import requests
    from .steps.animate import HF_SPACE
    r = requests.get(f"https://huggingface.co/api/spaces/{HF_SPACE}", timeout=45)
    r.raise_for_status()
    stage = (r.json().get("runtime") or {}).get("stage")
    if stage != "RUNNING":
        raise RuntimeError(f"Space อยู่สถานะ {stage} ไม่ใช่ RUNNING")
    return f"{HF_SPACE} กำลังทำงาน"


def check_kaggle(cfg: dict) -> str:
    from .steps import kaggle_gpu
    kaggle_gpu._run(["kernels", "list", "--mine", "--page-size", "1"], timeout=120)
    return "เชื่อมต่อได้"


def check_youtube(cfg: dict) -> str:
    """ตัวสำคัญที่สุด — refresh token ตายคือระบบหยุดเงียบ ๆ"""
    from .steps import upload
    yt = upload.client()          # ตรงนี้บังคับให้ refresh token ถูกใช้จริง
    r = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = r.get("items", [])
    if not items:
        raise RuntimeError("token ใช้ได้แต่ไม่พบช่องในบัญชีนี้")
    c = items[0]
    stats = c.get("statistics", {})
    return (f"{c['snippet']['title']} | ผู้ติดตาม {stats.get('subscriberCount','?')} "
            f"| คลิป {stats.get('videoCount','?')}")


CHECKS = [
    ("youtube", True, check_youtube),
    ("pollinations", True, check_pollinations),
    ("edge-tts", False, check_edge_tts),
    ("gemini", False, check_gemini),
    ("kaggle", False, check_kaggle),
    ("huggingface", False, check_huggingface),
]


def main(argv: list[str] | None = None) -> int:
    import argparse
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--channel", help="ช่องที่จะตรวจ")
    config.use(args.parse_args(argv).channel)

    cfg = config.load()
    report = config.docs_dir() / "health.json"
    results = [_check(name, essential, lambda f=fn: f(cfg)) for name, essential, fn in CHECKS]

    broken_essential = [r for r in results if not r["ok"] and r["essential"]]
    degraded = [r for r in results if not r["ok"] and not r["essential"]]

    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "channel": config.channel(),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "healthy": not broken_essential,
        "checks": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in results:
        mark = "ok  " if r["ok"] else ("ล้ม!" if r["essential"] else "เตือน")
        print(f"  [{mark}] {r['name']:<14} {r['detail']}")

    if degraded:
        print(f"\nมีตัวสำรองล้ม {len(degraded)} ตัว — ระบบยังเดินได้แต่คุณภาพจะลด")
    if broken_essential:
        print(f"\nตัวจำเป็นล้ม {len(broken_essential)} ตัว — รอบผลิตจะไม่ได้คลิป")
        return 1

    print("\nพร้อมผลิต")
    return 0


if __name__ == "__main__":
    sys.exit(main())
