"""สร้างภาพประกอบผ่าน Pollinations

ใช้ endpoint ใหม่ gen.pollinations.ai พร้อม Bearer token — ตัวเก่า image.pollinations.ai
แปะลายน้ำ pollinations.ai มุมล่างขวาทุกใบ และไม่สนใจ token ที่ส่งไปไม่ว่าจะส่งแบบไหน
"""
import time
import urllib.parse

import requests

from ..config import secret

BASE = "https://gen.pollinations.ai/image/"


def build_prompt(scene_prompt: str, character_sheet: str, style: str,
                 has_main_character: bool = True) -> str:
    """ประกอบ prompt ของฉาก

    แปะ character_sheet เฉพาะฉากที่มีตัวเอกจริง ๆ ถ้าแปะทุกฉาก โมเดลจะลากหน้าตาตัวเอก
    ไปใส่ในฉากที่ควรเป็นตัวละครอื่น เช่นฉากของคนแก่ก็จะกลายเป็นเด็กไปด้วย
    """
    parts = [scene_prompt]
    if has_main_character and character_sheet:
        parts.append(f"Main character: {character_sheet}")
    parts.append(f"Style: {style}")
    return ". ".join(parts)


MIN_IMAGE_BYTES = 5_000


def _try_model(prompt: str, out_path, cfg: dict, seed: int, model: str,
               attempts: int) -> None:
    url = BASE + urllib.parse.quote(prompt, safe="")
    params = {
        "width": cfg["images"].get("width") or cfg["video"]["width"],
        "height": cfg["images"].get("height") or cfg["video"]["height"],
        "model": model,
        "seed": seed,
        "nologo": "true",
    }
    headers = {"Authorization": f"Bearer {secret('POLLINATIONS_TOKEN')}"}

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=180)
            response.raise_for_status()
            if not response.headers.get("content-type", "").startswith("image"):
                raise RuntimeError(f"ไม่ได้ภาพกลับมา: {response.text[:120]}")
            if len(response.content) < MIN_IMAGE_BYTES:
                raise RuntimeError("ไฟล์ภาพเล็กผิดปกติ น่าจะยังสร้างไม่เสร็จ")
            with open(out_path, "wb") as fh:
                fh.write(response.content)
            return
        except Exception as exc:  # noqa: BLE001 - บริการฟรี ล้มได้หลายแบบ
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(str(last_error))


def fetch(prompt: str, out_path, cfg: dict, seed: int, attempts: int = 3) -> str:
    """ดึงภาพ 1 ใบ ไล่ลองทีละรุ่นจนกว่าจะได้ คืนชื่อรุ่นที่สำเร็จ

    แต่ละรุ่นลองซ้ำเองก่อน (บริการฟรีล่มชั่วคราวบ่อย) ถ้ายังไม่ได้ค่อยเปลี่ยนรุ่น
    กันกรณีรุ่นใดรุ่นหนึ่งถูกถอดออกหรือล่มยาว ซึ่งเกิดขึ้นจริงกับโมเดลชุมชน
    """
    errors = []
    for model in cfg["images"]["models"]:
        try:
            _try_model(prompt, out_path, cfg, seed, model, attempts)
            return model
        except Exception as exc:  # noqa: BLE001 - ลองรุ่นถัดไป
            short = model.split("/")[-1]
            print(f"      ภาพจาก {short} ไม่สำเร็จ: {str(exc)[:110]} — ลองรุ่นถัดไป")
            errors.append(f"{short}: {exc}")

    raise RuntimeError("สร้างภาพไม่สำเร็จทุกรุ่น:\n  " + "\n  ".join(e[:150] for e in errors))
