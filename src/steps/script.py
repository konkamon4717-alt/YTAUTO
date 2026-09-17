"""ให้ Gemini คิดพล็อต เขียนนิทาน แตกเป็นฉาก และเขียน metadata สำหรับอัปโหลด"""
import json

import requests

from ..config import secret

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SCHEMA = {
    "type": "object",
    "properties": {
        "premise": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "character_sheet": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "has_main_character": {"type": "boolean"},
                },
                "required": ["narration", "image_prompt", "has_main_character"],
            },
        },
        "localizations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lang": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["lang", "title", "description"],
            },
        },
    },
    "required": ["premise", "title", "description", "hashtags", "character_sheet", "scenes", "localizations"],
}

PROMPT = """คุณเป็นนักเขียนนิทานสั้นสำหรับคลิป YouTube Shorts ภาษาไทย

เขียนนิทาน 1 เรื่อง จบในตอนเดียว ความยาวเมื่ออ่านออกเสียงประมาณ {target} วินาที (ห้ามเกิน {hard_max} วินาที)

ข้อกำหนดของเรื่อง:
- ฮุก 3 วินาทีแรกต้องทำให้คนหยุดนิ้ว เปิดด้วยเหตุการณ์หรือคำถาม ห้ามเปิดด้วย "กาลครั้งหนึ่ง"
- มีจุดหักมุมหรือบทเรียนที่คนอ่านคาดไม่ถึงในตอนจบ
- ภาษาไทยที่เป็นธรรมชาติ เล่าเหมือนคนเล่า ไม่ใช่ภาษาเขียนแข็ง ๆ
- ห้ามใช้สำนวนแปลจากอังกฤษ
- ปิดท้ายด้วยประโยคสั้นที่คนอยากคอมเมนต์ตอบ

แตกเป็น {scenes} ฉาก แต่ละฉาก:
- narration: บทพากย์ของฉากนั้น 1-2 ประโยค ห้ามมีเครื่องหมายวงเล็บหรือคำกำกับใด ๆ เพราะจะถูกอ่านออกเสียงทั้งหมด
- image_prompt: คำสั่งสร้างภาพ "ภาษาอังกฤษ" บรรยายสิ่งที่เห็นในฉากนั้น ห้ามมีตัวหนังสือในภาพ
- has_main_character: true ถ้าฉากนั้นเห็นตัวเอก, false ถ้าเป็นฉากของตัวละครอื่นหรือฉากวิวเปล่า
  ตอบให้ตรง เพราะถ้าตอบ true ผิด ๆ ในฉากที่ควรเป็นคนแก่ ภาพจะออกมาเป็นตัวเอกแทน

character_sheet: บรรยาย "หน้าตาและเสื้อผ้า" ของตัวละครหลักเป็นภาษาอังกฤษ ไม่เกิน 20 คำ
ระบุแค่ อายุ ทรงผม สีและแบบเสื้อผ้า เท่านั้น
ห้ามใส่สิ่งของที่ถืออยู่ ห้ามใส่ท่าทาง ห้ามใส่ฉากหลัง เพราะข้อความนี้จะถูกแปะเข้าไปในทุกฉาก
ถ้าใส่ "ถือตะกร้าไข่" ตัวละครจะถือตะกร้าไข่ทุกฉากแม้แต่ฉากที่ไม่ควรถือ

title: ชื่อคลิปภาษาไทย ไม่เกิน 70 ตัวอักษร ชวนคลิกแต่ห้ามเกินจริง
description: คำอธิบาย 2-3 บรรทัด
hashtags: 5-8 อัน ไม่ต้องใส่ #
localizations: แปลชื่อคลิปและคำอธิบายเป็นภาษา {locales} (ให้เป็นธรรมชาติในภาษานั้น ไม่ใช่แปลตรงตัว)

ห้ามใช้พล็อตที่ซ้ำหรือใกล้เคียงกับรายการนี้:
{avoid}
"""


def generate(cfg: dict, avoid: list[str]) -> dict:
    avoid_text = "\n".join(f"- {p}" for p in avoid) if avoid else "- (ยังไม่มี เป็นเรื่องแรก)"
    prompt = PROMPT.format(
        target=cfg["video"]["target_seconds"],
        hard_max=cfg["video"]["hard_max_seconds"],
        scenes=cfg["images"]["scenes"],
        locales=", ".join(cfg["upload"]["localizations"]),
        avoid=avoid_text,
    )

    response = requests.post(
        ENDPOINT.format(model=cfg["llm"]["model"]),
        params={"key": secret("GEMINI_API_KEY")},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1.1,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        },
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Gemini ตอบกลับผิดรูปแบบ: {json.dumps(payload)[:500]}") from exc

    story = json.loads(text)
    if not story.get("scenes"):
        raise RuntimeError("Gemini ไม่ได้ส่งฉากกลับมา")
    return story
