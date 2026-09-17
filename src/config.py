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


def load() -> dict:
    _load_dotenv()
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def secret(name: str, required: bool = True) -> str:
    # เรียก secret() ตรง ๆ ได้โดยไม่ต้อง load() ก่อน — สคริปต์เล็ก ๆ จะได้ไม่พลาด
    _load_dotenv()
    value = os.environ.get(name, "")
    if required and not value:
        raise RuntimeError(
            f"ไม่พบค่า {name} — ใส่ใน .env (เครื่องตัวเอง) หรือ Repository secrets (GitHub Actions)"
        )
    return value
