"""พากย์เสียงด้วย edge-tts พร้อมดึงจังหวะของแต่ละคำมาทำซับ"""
import asyncio

import edge_tts

TICKS_PER_SECOND = 10_000_000  # edge-tts ให้เวลามาเป็นหน่วย 100 นาโนวินาที


async def _synth(text: str, out_path, cfg: dict) -> list[dict]:
    tts = cfg["tts"]
    # ตั้งแต่ edge-tts 7.x ต้องสั่ง boundary="WordBoundary" เอง ไม่งั้นได้แค่ระดับประโยค
    # แล้วซับจะว่างเปล่า — ตัวนี้แบ่งคำไทย (ที่เขียนติดกัน) ได้ถูกต้องด้วย
    communicate = edge_tts.Communicate(
        text, tts["voice"], rate=tts["rate"], pitch=tts["pitch"],
        boundary="WordBoundary",
    )
    words: list[dict] = []
    with open(out_path, "wb") as fh:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append(
                    {
                        "text": chunk["text"],
                        "start": start,
                        "end": start + chunk["duration"] / TICKS_PER_SECOND,
                    }
                )
    return words


def speak(text: str, out_path, cfg: dict) -> list[dict]:
    """สร้างไฟล์เสียง แล้วคืนรายการคำพร้อมเวลาเริ่ม/จบ (วินาที)"""
    return asyncio.run(_synth(text, out_path, cfg))
