"""โหลด config.yaml + ตัวแปรลับจาก environment (หรือไฟล์ .env ตอนรันในเครื่อง)"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
DATA = ROOT / "data"
ASSETS = ROOT / "assets"


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


LOCAL = ROOT / "config.local.yaml"


def _merge(base: dict, over: dict) -> dict:
    """ทับค่าแบบลงลึก ทับเฉพาะคีย์ที่มีจริง ไม่ลบของเดิมทิ้ง"""
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    """อ่าน config.yaml แล้วทับด้วย config.local.yaml ถ้ามี

    แยกเป็นสองไฟล์เพราะห้องควบคุมต้องเขียนค่ากลับได้ แต่ PyYAML เขียนกลับแล้ว
    คอมเมนต์อธิบายทั้งหมดจะหายไป การให้หน้าเว็บเขียนเฉพาะไฟล์ทับค่า
    ทำให้ config.yaml ยังเป็นเอกสารที่อ่านรู้เรื่อง และเห็นชัดว่าอะไรถูกแก้จากหน้าเว็บ
    """
    _load_dotenv()
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    if LOCAL.exists():
        with open(LOCAL, encoding="utf-8") as fh:
            cfg = _merge(cfg, yaml.safe_load(fh) or {})
    return cfg


def save_overrides(patch: dict) -> dict:
    """เขียนค่าที่แก้จากหน้าเว็บลง config.local.yaml แล้วคืน config ที่ใช้จริง"""
    current = {}
    if LOCAL.exists():
        with open(LOCAL, encoding="utf-8") as fh:
            current = yaml.safe_load(fh) or {}

    merged = _merge(current, patch)
    LOCAL.write_text(
        "# ค่าที่แก้จากห้องควบคุม — ทับค่าใน config.yaml\n"
        "# ลบไฟล์นี้ทิ้งเมื่อไหร่ ระบบจะกลับไปใช้ค่าตั้งต้นทั้งหมด\n"
        + yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return load()


def secret(name: str, required: bool = True) -> str:
    # เรียก secret() ตรง ๆ ได้โดยไม่ต้อง load() ก่อน — สคริปต์เล็ก ๆ จะได้ไม่พลาด
    _load_dotenv()
    value = os.environ.get(name, "")
    if required and not value:
        raise RuntimeError(
            f"ไม่พบค่า {name} — ใส่ใน .env (เครื่องตัวเอง) หรือ Repository secrets (GitHub Actions)"
        )
    return value
