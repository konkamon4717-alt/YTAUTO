"""ให้ Gemini คิดพล็อต เขียนนิทาน แตกเป็นฉาก และเขียน metadata สำหรับอัปโหลด"""
import json
import time

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
                    "motion": {"type": "string"},
                    "importance": {"type": "integer"},
                },
                "required": ["narration", "image_prompt", "has_main_character",
                             "motion", "importance"],
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
- narration: บทพากย์ของฉากนั้น **สั้น ๆ ประมาณ 4-5 วินาทีเมื่ออ่านออกเสียง** (ราว 1 ประโยค)
  ห้ามมีเครื่องหมายวงเล็บหรือคำกำกับใด ๆ เพราะจะถูกอ่านออกเสียงทั้งหมด
- motion: สิ่งที่ "เคลื่อนไหว" ในฉากนั้น เป็นภาษาอังกฤษสั้น ๆ เช่น
  "she slowly turns her head, wind moves her hair" หรือ "camera pushes in, steam rises from the bowl"
  ให้เป็นการเคลื่อนไหวที่ช้าและเล็กน้อย ห้ามสั่งให้เดิน วิ่ง หรือเปลี่ยนท่าใหญ่ ๆ
  เพราะโมเดลวิดีโอจะทำหน้าตัวละครบิดเบี้ยว
- importance: 1-5 ความสำคัญของฉาก ให้ 5 กับฉากเปิด (ฮุก) และฉากหักมุม
  ใช้จัดลำดับว่าฉากไหนควรได้คิวทำภาพเคลื่อนไหวก่อนเมื่อโควต้ามีจำกัด
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


POLLINATIONS_ENDPOINT = "https://gen.pollinations.ai/v1/chat/completions"

RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_WAITS = (5, 15, 40)


def _post(url: str, *, headers: dict, payload: dict, timeout: int) -> dict:
    """ยิง POST พร้อมลองใหม่เมื่อเจอ error ชั่วคราว

    ข้อความ error ของ requests บอกแค่รหัสสถานะ ไม่บอก body ซึ่งเป็นที่อยู่ของเหตุผลจริง
    (เช่น "temperature ต้องไม่เกิน 1.0") เลยต้องแนบ body มาด้วยเสมอ
    """
    last = ""
    for attempt in range(len(RETRY_WAITS) + 1):
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if response.ok:
            return response.json()

        last = f"HTTP {response.status_code}: {response.text[:300]}"
        if response.status_code not in RETRY_STATUSES or attempt == len(RETRY_WAITS):
            break
        wait = RETRY_WAITS[attempt]
        print(f"      ติด {response.status_code} ลองใหม่ใน {wait} วินาที")
        time.sleep(wait)

    raise RuntimeError(last)


def _gemini(prompt: str, cfg: dict) -> dict:
    payload = _post(
        ENDPOINT.format(model=cfg["llm"]["model"]),
        # ส่งคีย์ทาง header ไม่ใช่ ?key= เพราะค่าใน URL จะติดไปกับข้อความ error และ log
        headers={"x-goog-api-key": secret("GEMINI_API_KEY")},
        payload={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1.1,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        },
        timeout=180,
    )
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"ตอบกลับผิดรูปแบบ: {json.dumps(payload)[:300]}") from exc
    return json.loads(text)


def _pollinations(prompt: str, cfg: dict) -> dict:
    """ตัวสำรอง ใช้โมเดลฟรีของ Pollinations

    ตัวนี้ไม่รับ responseSchema แบบ Gemini เลยต้องอธิบายโครงสร้างไปในคำสั่งแทน
    แล้วสั่งให้ตอบเป็น json_object
    """
    full = (
        f"{prompt}\n\n"
        "ตอบเป็น JSON ล้วน ๆ เท่านั้น ห้ามมีข้อความอื่นนอก JSON "
        "ห้ามครอบด้วย markdown code fence\n"
        f"โครงสร้างที่ต้องตอบ:\n{json.dumps(SCHEMA, ensure_ascii=False)}"
    )
    payload = _post(
        POLLINATIONS_ENDPOINT,
        headers={"Authorization": f"Bearer {secret('POLLINATIONS_TOKEN')}",
                 "Content-Type": "application/json"},
        payload={
            "model": cfg["llm"]["fallback_model"],
            "messages": [{"role": "user", "content": full}],
            "response_format": {"type": "json_object"},
            # โมเดลชุมชนหลายตัวไม่ยอมรับ temperature เกิน 1.0 — 1.0 คือค่าสูงสุดที่ปลอดภัย
            "temperature": 1.0,
            "max_tokens": 8000,
        },
        timeout=240,
    )
    text = payload["choices"][0]["message"]["content"]
    return json.loads(_strip_fence(text))


def _strip_fence(text: str) -> str:
    """โมเดลบางตัวชอบครอบคำตอบด้วย ```json แม้จะสั่งห้ามแล้ว"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _validate(story: dict, cfg: dict) -> None:
    """เช็คว่าได้ของครบก่อนเอาไปใช้ ดีกว่าไปพังตอนเรนเดอร์ไปแล้วครึ่งทาง"""
    scenes = story.get("scenes") or []
    if len(scenes) < 3:
        raise RuntimeError(f"ได้ฉากมาแค่ {len(scenes)} ฉาก น้อยเกินไป")
    for index, scene in enumerate(scenes):
        if not scene.get("narration", "").strip():
            raise RuntimeError(f"ฉาก {index + 1} ไม่มีบทพากย์")
        if not scene.get("image_prompt", "").strip():
            raise RuntimeError(f"ฉาก {index + 1} ไม่มีคำสั่งสร้างภาพ")
        scene.setdefault("motion", "")
        scene.setdefault("importance", 3)
        scene.setdefault("has_main_character", True)
    if not story.get("title", "").strip():
        raise RuntimeError("ไม่มีชื่อคลิป")
    story.setdefault("premise", story["title"])
    story.setdefault("description", story["title"])
    story.setdefault("hashtags", [])
    story.setdefault("character_sheet", "")
    story.setdefault("localizations", [])


BACKENDS = {"gemini": _gemini, "pollinations": _pollinations}


def generate(cfg: dict, avoid: list[str]) -> dict:
    """เขียนบทด้วยผู้ให้บริการตัวแรกที่ใช้ได้ ตกไปตัวถัดไปเมื่อเจ๊ง

    เคยเจอมาแล้วว่าโปรเจกต์ Gemini ถูกบล็อกทั้งยวงโดยไม่มีสัญญาณล่วงหน้า
    การมีตัวสำรองทำให้ระบบไม่หยุดเดินเพราะผู้ให้บริการรายเดียว
    """
    avoid_text = "\n".join(f"- {p}" for p in avoid) if avoid else "- (ยังไม่มี เป็นเรื่องแรก)"
    prompt = PROMPT.format(
        target=cfg["video"]["target_seconds"],
        hard_max=cfg["video"]["hard_max_seconds"],
        scenes=cfg["images"]["scenes"],
        locales=", ".join(cfg["upload"]["localizations"]),
        avoid=avoid_text,
    )

    errors = []
    for name in cfg["llm"]["backends"]:
        backend = BACKENDS.get(name)
        if not backend:
            continue
        try:
            story = backend(prompt, cfg)
            _validate(story, cfg)
            story["_writer"] = name
            return story
        except Exception as exc:  # noqa: BLE001 - ลองตัวถัดไปเสมอ
            message = f"{name}: {type(exc).__name__}: {str(exc)[:150]}"
            print(f"      เขียนบทด้วย {message} — ลองตัวถัดไป")
            errors.append(message)

    raise RuntimeError("เขียนบทไม่สำเร็จทุกตัว:\n  " + "\n  ".join(errors))
