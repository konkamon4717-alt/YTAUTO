"""โหลด config ของช่อง + ตัวแปรลับจาก environment (หรือไฟล์ .env ตอนรันในเครื่อง)

ระบบนี้รันได้หลายช่องจากโค้ดชุดเดียว แต่ละช่องมีโฟลเดอร์ของตัวเองใน channels/
และมีไฟล์ข้อมูลแยกกันใน data/<ช่อง>/ กับ docs/<ช่อง>/

ที่ไม่แยกเป็นคนละ repo เพราะทุกบั๊กที่เจอจะต้องไปไล่แก้ทุก repo
ยิ่งมีหลายช่องยิ่งแก้หลายที่ สุดท้ายจะมีช่องที่ตกรุ่นแล้วพังเงียบ ๆ

ทุกคำสั่งรับ --channel ได้ ถ้าไม่ใส่จะใช้ค่าจาก YT_CHANNEL หรือช่องตั้งต้น
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
ASSETS = ROOT / "assets"
CHANNELS = ROOT / "channels"

DEFAULT_CHANNEL = "nithan"
_current = os.environ.get("YT_CHANNEL") or DEFAULT_CHANNEL


def use(name: str | None) -> str:
    """เลือกช่องที่จะทำงานด้วยในกระบวนการนี้ ส่ง None มาได้ถ้าจะใช้ค่าเดิม"""
    global _current
    if name:
        if not (CHANNELS / name / "config.yaml").exists():
            raise RuntimeError(f"ไม่พบช่องชื่อ {name} ใน {CHANNELS}")
        _current = name
    return _current


def channel() -> str:
    return _current


def available() -> list[str]:
    if not CHANNELS.exists():
        return []
    return sorted(p.name for p in CHANNELS.iterdir() if (p / "config.yaml").exists())


# ---------- เส้นทางไฟล์ของช่องที่กำลังใช้ ----------
# เป็นฟังก์ชันไม่ใช่ค่าคงที่ เพราะช่องเปลี่ยนได้หลัง import แล้ว
# ถ้าเก็บเป็นค่าคงที่ตอน import จะได้เส้นทางของช่องตั้งต้นค้างไว้ตลอด

def channel_dir() -> Path:
    return CHANNELS / _current


def data_dir() -> Path:
    return ROOT / "data" / _current


def docs_dir() -> Path:
    return ROOT / "docs" / _current


def work_dir() -> Path:
    return OUT / _current


def _load_dotenv() -> None:
    """อ่าน .env แบบง่าย ๆ ใช้เฉพาะตอนรันในเครื่อง บน Actions จะใช้ env จริง"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _merge(base: dict, over: dict) -> dict:
    """ทับค่าแบบลงลึก ทับเฉพาะคีย์ที่มีจริง ไม่ลบของเดิมทิ้ง"""
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def local_path() -> Path:
    return channel_dir() / "config.local.yaml"


def load() -> dict:
    """อ่าน config.yaml ของช่อง แล้วทับด้วย config.local.yaml ถ้ามี

    แยกเป็นสองไฟล์เพราะห้องควบคุมต้องเขียนค่ากลับได้ แต่ PyYAML เขียนกลับแล้ว
    คอมเมนต์อธิบายทั้งหมดจะหายไป การให้หน้าเว็บเขียนเฉพาะไฟล์ทับค่า
    ทำให้ config.yaml ยังเป็นเอกสารที่อ่านรู้เรื่อง และเห็นชัดว่าอะไรถูกแก้จากหน้าเว็บ
    """
    _load_dotenv()
    with open(channel_dir() / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    local = local_path()
    if local.exists():
        with open(local, encoding="utf-8") as fh:
            cfg = _merge(cfg, yaml.safe_load(fh) or {})

    cfg["_channel"] = _current
    return cfg


def save_overrides(patch: dict) -> dict:
    """เขียนค่าที่แก้จากหน้าเว็บลง config.local.yaml ของช่องนี้ แล้วคืน config ที่ใช้จริง"""
    local = local_path()
    current = {}
    if local.exists():
        with open(local, encoding="utf-8") as fh:
            current = yaml.safe_load(fh) or {}

    merged = _merge(current, patch)
    local.write_text(
        f"# ค่าที่แก้จากห้องควบคุมของช่อง {_current} — ทับค่าใน config.yaml\n"
        "# ลบไฟล์นี้ทิ้งเมื่อไหร่ ระบบจะกลับไปใช้ค่าตั้งต้นทั้งหมด\n"
        + yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return load()


def secret(name: str, required: bool = True) -> str:
    """หาค่าลับของช่องนี้ก่อน ถ้าไม่มีค่อยใช้ตัวกลางที่ทุกช่องใช้ร่วมกัน

    เช่นช่อง world จะหา YT_REFRESH_TOKEN_WORLD ก่อน เพราะโทเค็นยูทูปต้องแยกต่อช่อง
    ส่วน GEMINI_API_KEY ไม่ต้องแยก ทุกช่องใช้ตัวเดียวกันได้ จึงตกมาที่ชื่อกลาง
    วิธีนี้ทำให้เพิ่มช่องใหม่ตั้ง secret เท่าที่จำเป็นจริง ๆ ไม่ต้องตั้งซ้ำทั้งชุด
    """
    _load_dotenv()
    scoped = f"{name}_{_current.upper()}"
    value = os.environ.get(scoped) or os.environ.get(name, "")
    if required and not value:
        raise RuntimeError(
            f"ไม่พบค่า {scoped} หรือ {name} — ใส่ใน .env (เครื่องตัวเอง) "
            "หรือ Repository secrets (GitHub Actions)"
        )
    return value


# เข้ากันได้กับโค้ดเดิมที่ยังอ้าง config.DATA ตรง ๆ
DATA = ROOT / "data"
