"""สร้างภาพประกอบผ่าน Pollinations (ฟรี ไม่ต้องใช้ API key)"""
import time
import urllib.parse

import requests

BASE = "https://image.pollinations.ai/prompt/"


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


def fetch(prompt: str, out_path, cfg: dict, seed: int, attempts: int = 4) -> None:
    """ดึงภาพ 1 ใบ ถ้าเซิร์ฟเวอร์ฟรีล่มก็ลองใหม่แบบถอยเวลาเพิ่มขึ้น"""
    url = BASE + urllib.parse.quote(prompt, safe="")
    params = {
        "width": cfg["video"]["width"],
        "height": cfg["video"]["height"],
        "model": cfg["images"]["model"],
        "seed": seed,
        "nologo": "true",
        "referrer": "yt-auto",
    }

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=180)
            response.raise_for_status()
            if not response.content or len(response.content) < 5_000:
                raise RuntimeError("ได้ไฟล์ภาพเล็กผิดปกติ น่าจะยังไม่เสร็จ")
            with open(out_path, "wb") as fh:
                fh.write(response.content)
            return
        except Exception as exc:  # noqa: BLE001 - บริการฟรี ล้มได้หลายแบบ
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))

    raise RuntimeError(f"สร้างภาพไม่สำเร็จหลังลอง {attempts} ครั้ง: {last_error}")
