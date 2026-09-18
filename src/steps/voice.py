"""พากย์เสียง พร้อมตัวสำรองหลายชั้น

edge-tts เป็นตัวหลักเพราะฟรี เสียงไทยดี และ**คืนจังหวะของแต่ละคำมาให้ด้วย**
ซึ่งเราเอาไปทำซับที่ตรงกับเสียงเป๊ะ ๆ ได้โดยไม่ต้องใช้ Whisper

ปัญหาคือ edge-tts เคยถูก Microsoft บล็อกมาแล้วจริง (403) การมีแต่ตัวนี้ตัวเดียว
แปลว่าวันที่เขาบล็อกอีกครั้ง ระบบจะไม่ได้คลิปเลย

ตัวสำรองไม่คืนจังหวะคำมาให้ เลยต้องเปลี่ยนวิธี: แบ่งบทเป็นวรรคแล้วพากย์ทีละวรรค
ความยาวของไฟล์เสียงแต่ละวรรคคือจังหวะของซับไปในตัว ได้ซับที่ยังตรงกับเสียงอยู่
แค่หยาบกว่าระดับคำเท่านั้น
"""
import asyncio
import time
import os
import subprocess
from pathlib import Path

TICKS_PER_SECOND = 10_000_000  # edge-tts ให้เวลามาเป็นหน่วย 100 นาโนวินาที
MAX_PHRASE_CHARS = 42


class VoiceResult(dict):
    """{'backend': str, 'granularity': 'word'|'phrase', 'segments': [{text,start,end}]}"""


# ---------- ตัวหลัก: edge-tts ----------

async def _edge_stream(text: str, out_path: Path, cfg: dict) -> list[dict]:
    import edge_tts

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
                words.append({
                    "text": chunk["text"],
                    "start": start,
                    "end": start + chunk["duration"] / TICKS_PER_SECOND,
                })
    if not words:
        raise RuntimeError("edge-tts ไม่ได้ส่งจังหวะคำกลับมา")
    return words


EDGE_RETRIES = 3
EDGE_WAIT = 4


def _edge(text: str, out_path: Path, cfg: dict) -> VoiceResult:
    """edge-tts ล้มแบบชั่วคราวบ่อย (NoAudioReceived) ลองซ้ำก่อนยอมแพ้

    สำคัญกว่าที่คิด เพราะการถอยไปตัวสำรองแปลว่า "เปลี่ยนเสียงพากย์"
    ซึ่งผู้ฟังจับได้ทันที การลองซ้ำสองสามครั้งจึงคุ้มกว่าเปลี่ยนเสียง
    """
    last: Exception | None = None
    for attempt in range(EDGE_RETRIES):
        try:
            words = asyncio.run(_edge_stream(text, out_path, cfg))
            return VoiceResult(backend="edge-tts", granularity="word", segments=words)
        except Exception as exc:  # noqa: BLE001 - ล้มชั่วคราว ลองใหม่
            last = exc
            if attempt < EDGE_RETRIES - 1:
                time.sleep(EDGE_WAIT * (attempt + 1))
    raise RuntimeError(f"ลอง {EDGE_RETRIES} ครั้งแล้วยังไม่ได้: {last}")


# ---------- ตัวสำรอง: พากย์ทีละวรรค ----------

def split_phrases(text: str) -> list[str]:
    """แบ่งบทเป็นวรรคตามช่องว่างที่คนเขียนใส่ไว้

    ภาษาไทยไม่มีช่องว่างระหว่างคำ ช่องว่างที่มีจึงเป็นการแบ่งวรรคโดยตั้งใจ
    วรรคไหนยาวเกินก็ปล่อยไว้ ดีกว่าตัดมั่วจนอ่านไม่รู้เรื่อง
    """
    parts = [p.strip() for p in text.split() if p.strip()]
    if not parts:
        return [text]

    phrases: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > MAX_PHRASE_CHARS:
            phrases.append(current)
            current = part
        else:
            current = candidate
    if current:
        phrases.append(current)
    return phrases


def _pollinations_audio(text: str, out_path: Path, cfg: dict) -> None:
    import requests
    from ..config import secret

    response = requests.post(
        "https://gen.pollinations.ai/v1/audio/speech",
        headers={"Authorization": f"Bearer {secret('POLLINATIONS_TOKEN')}",
                 "Content-Type": "application/json"},
        json={"model": cfg["tts"]["pollinations_model"], "input": text},
        timeout=180,
    )
    response.raise_for_status()
    if "audio" not in response.headers.get("content-type", ""):
        raise RuntimeError(f"ไม่ได้ไฟล์เสียงกลับมา: {response.text[:150]}")
    out_path.write_bytes(response.content)


def _gtts_audio(text: str, out_path: Path, cfg: dict) -> None:
    from gtts import gTTS
    gTTS(text, lang=cfg["channel"]["language"]).save(str(out_path))


PHRASE_BACKENDS = {
    "pollinations": _pollinations_audio,
    "gtts": _gtts_audio,
}


def _duration(path: Path) -> float:
    import json
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"อ่านความยาวไฟล์เสียงไม่ได้: {path.name}")
    return float(json.loads(result.stdout)["format"]["duration"])


def _speak_by_phrase(name: str, text: str, out_path: Path, cfg: dict) -> VoiceResult:
    synth = PHRASE_BACKENDS[name]
    work = out_path.parent / f"_ph_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)

    phrases = split_phrases(text)
    parts: list[Path] = []
    segments: list[dict] = []
    offset = 0.0

    for index, phrase in enumerate(phrases):
        part = work / f"{index:02d}.mp3"
        synth(phrase, part, cfg)
        seconds = _duration(part)
        segments.append({"text": phrase, "start": offset, "end": offset + seconds})
        parts.append(part)
        offset += seconds

    # ต้องเป็น path แบบเต็ม เพราะ FFmpeg หาไฟล์ในรายการนี้โดยอิงจากตำแหน่งของ
    # ไฟล์รายการเอง ไม่ใช่จากที่รันคำสั่ง ใส่ path สัมพัทธ์ลงไปมันจะไปหาซ้อนอีกชั้น
    listing = work / "concat.txt"
    listing.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts) + "\n",
        encoding="utf-8")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("ต่อไฟล์เสียงไม่สำเร็จ:\n" + result.stderr[-400:])

    return VoiceResult(backend=name, granularity="phrase", segments=segments)


# ---------- ทางเข้าหลัก ----------

def _speak_one(name: str, text: str, out_path: Path, cfg: dict) -> VoiceResult:
    if name == "edge-tts":
        return _edge(text, out_path, cfg)
    if name in PHRASE_BACKENDS:
        return _speak_by_phrase(name, text, out_path, cfg)
    raise RuntimeError(f"ไม่รู้จักตัวพากย์ {name}")


def speak_all(texts: list[str], out_paths: list[Path], cfg: dict) -> list[VoiceResult]:
    """พากย์ทั้งคลิปด้วยเสียงเดียวกัน

    ต้องเลือกตัวพากย์ "ครั้งเดียวต่อคลิป" ไม่ใช่ทีละฉาก เพราะแต่ละตัวเสียงคนละคน
    ของเดิมเลือกทีละฉาก พอ edge-tts ล้มบางฉากเลยได้คลิปที่เสียงผู้หญิงสลับผู้ชาย
    กลางเรื่อง ซึ่งผู้ฟังจับได้ทันทีและทำลายเอกลักษณ์ของช่อง

    ตัวไหนทำไม่ครบทุกฉาก ถือว่าใช้ไม่ได้ทั้งตัว แล้วเริ่มใหม่ด้วยตัวถัดไป
    """
    errors = []
    for name in cfg["tts"]["backends"]:
        try:
            results = [
                _speak_one(name, text, Path(path), cfg)
                for text, path in zip(texts, out_paths)
            ]
            if name != cfg["tts"]["backends"][0]:
                print(f"      พากย์ทั้งคลิปด้วยเสียงสำรอง '{name}'")
            return results
        except Exception as exc:  # noqa: BLE001 - ทั้งตัวใช้ไม่ได้ ไปตัวถัดไป
            message = f"{name}: {type(exc).__name__}: {str(exc)[:110]}"
            print(f"      พากย์ด้วย {message}")
            print(f"      — เปลี่ยนตัวพากย์ทั้งคลิป ไม่ผสมเสียงกลางเรื่อง")
            errors.append(message)

    raise RuntimeError("พากย์เสียงไม่สำเร็จทุกตัว:\n  " + "\n  ".join(errors))


def speak(text: str, out_path, cfg: dict) -> VoiceResult:
    """พากย์ฉากเดียว — ใช้ตอนทดสอบเท่านั้น ของจริงใช้ speak_all"""
    return speak_all([text], [Path(out_path)], cfg)[0]
