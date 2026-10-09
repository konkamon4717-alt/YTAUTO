"""หาภาพจริงจากคลังภาพเสรี แทนการให้ AI วาดขึ้นมาเอง

ช่องที่เล่าเรื่องจริง (ภูมิศาสตร์ ประวัติศาสตร์ วิทยาศาสตร์) ใช้ภาพที่ AI วาดไม่ได้
เพราะมันคือการสร้างภาพปลอมของสิ่งที่มีอยู่จริง คนดูเข้าใจผิดว่านี่คือภาพของจริง
และถ้าเป็นเหตุการณ์หรือบุคคลจริงก็ผิดนโยบายข้อมูลบิดเบือนของ YouTube ตรง ๆ

จึงค้นจากคลังที่ใช้ได้ฟรีเชิงพาณิชย์แทน เรียงตามความน่าจะเจอของที่ตรง:

  Wikimedia Commons  คลังใหญ่สุด มีทุกเรื่องบนโลก และบอกเจ้าของภาพมาครบ
  Openverse         รวมคลังอื่นไว้ที่เดียว ใช้เป็นตัวสำรองเวลา Commons ไม่มี
  NASA              ภาพอวกาศและโลกจากดาวเทียม เป็นสาธารณสมบัติทั้งหมด

ทุกภาพต้องมีเครดิตติดไปในคำอธิบายคลิป ไม่ใช่ความสุภาพแต่เป็นเงื่อนไขของสัญญาอนุญาต
ถ้าไม่ใส่ก็คือละเมิดลิขสิทธิ์เหมือนกับไปหยิบภาพมาเฉย ๆ
"""
import html
import re
import subprocess

import requests

UA = "yt-auto/1.0 (https://github.com/konkamon4717-alt/YTAUTO)"
TIMEOUT = 45
MIN_WIDTH = 900          # เล็กกว่านี้ขยายเป็นจอ 1080 แล้วเห็นเป็นหยัก

# Wikimedia Commons เก็บทุกอย่างไม่ใช่แค่ภาพถ่าย การค้นคำว่า "ocean current"
# จึงได้แผนผังลูกศร แผนที่โบราณ และหน้าเอกสารสแกนมาก่อนภาพถ่ายจริง
# ซึ่งบนคลิปสั้นคือภาพที่คนเลื่อนผ่านทันที ต้องคัดออกตั้งแต่ต้นทาง
NOT_A_PHOTO = (
    "map", "แผนที่", "diagram", "chart", "graph", "plot", "schematic",
    "logo", "flag", "coat of arms", "seal", "emblem", "banner",
    "poster", "stamp", "postcard", "manuscript", "document", "letter",
    "page", "cover", "title", "sheet music", "drawing", "sketch",
    "engraving", "illustration", "painting", "portrait of", "icon",
    "screenshot", "chess", "svg", "symbol", "sign",
)


def _looks_like_photo(title: str) -> bool:
    low = title.lower()
    return not any(word in low for word in NOT_A_PHOTO)


def _score(hit: dict, query: str) -> int:
    """ยิ่งคำในคำค้นโผล่ในชื่อไฟล์มาก ยิ่งน่าจะเป็นภาพที่ตรงเรื่องจริง

    ไม่ใช่การวัดที่แม่น แต่ดีกว่าเชื่อลำดับที่คลังส่งมา ซึ่งเรียงตามความ
    เกี่ยวข้องของข้อความทั้งหน้า ไม่ใช่ความเกี่ยวข้องของตัวภาพ
    """
    low = hit["title"].lower()
    return sum(1 for word in query.lower().split() if len(word) > 2 and word in low)


def _clean(text: str) -> str:
    """เครดิตจาก Commons มาเป็น HTML ต้องถอดแท็กก่อนเอาไปใส่คำอธิบายคลิป"""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


# ---------- คลังภาพแต่ละแห่ง ----------

def _wikimedia(query: str) -> list[dict]:
    r = requests.get("https://commons.wikimedia.org/w/api.php", timeout=TIMEOUT,
                     headers={"User-Agent": UA}, params={
        "action": "query", "format": "json",
        "generator": "search",
        # filetype:bitmap กัน svg และไฟล์เสียงที่หลุดมาในผลค้นหา
        # ปฏิเสธตั้งแต่ต้นทางได้ผลกว่ามากองกรองชื่อไฟล์ทีหลัง เพราะ Commons
        # เก็บเอกสารสแกน แผนที่โบราณ และภาพพิมพ์ไว้ปนกับภาพถ่ายทั้งหมด
        "gsrsearch": (f"{query} filetype:bitmap "
                      "-map -diagram -chart -painting -engraving -drawing "
                      "-lithograph -poster -stamp -manuscript -logo"),
        "gsrnamespace": 6, "gsrlimit": 12,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": 1600,
    })
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}

    out = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        if info.get("width", 0) < MIN_WIDTH:
            continue
        author = _clean(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons"
        licence = _clean(meta.get("LicenseShortName", {}).get("value", "")) or "ดูที่ต้นทาง"
        out.append({
            "url": info.get("thumburl") or info.get("url"),
            "title": page.get("title", "").replace("File:", ""),
            "author": author[:80],
            "license": licence,
            "source": info.get("descriptionurl", ""),
            "via": "Wikimedia Commons",
        })
    return out


def _openverse(query: str) -> list[dict]:
    r = requests.get("https://api.openverse.org/v1/images/", timeout=TIMEOUT,
                     headers={"User-Agent": UA}, params={
        "q": query,
        # ขอเฉพาะที่ใช้เชิงพาณิชย์และดัดแปลงได้ เพราะเราครอปและซ้อนตัวหนังสือทับ
        "license_type": "commercial,modification",
        "page_size": 12,
    })
    r.raise_for_status()
    out = []
    for item in r.json().get("results", []):
        if (item.get("width") or 0) < MIN_WIDTH:
            continue
        out.append({
            "url": item.get("url"),
            "title": item.get("title") or query,
            "author": (item.get("creator") or "ไม่ระบุชื่อ")[:80],
            "license": (item.get("license") or "").upper(),
            "source": item.get("foreign_landing_url") or item.get("url", ""),
            "via": "Openverse",
        })
    return out


def _nasa(query: str) -> list[dict]:
    r = requests.get("https://images-api.nasa.gov/search", timeout=TIMEOUT,
                     headers={"User-Agent": UA},
                     params={"q": query, "media_type": "image"})
    r.raise_for_status()
    out = []
    for item in (r.json().get("collection") or {}).get("items", [])[:12]:
        links = item.get("links") or []
        data = (item.get("data") or [{}])[0]
        if not links:
            continue
        out.append({
            "url": links[0].get("href"),
            "title": data.get("title") or query,
            "author": data.get("center") or "NASA",
            "license": "สาธารณสมบัติ",
            "source": f"https://images.nasa.gov/details/{data.get('nasa_id', '')}",
            "via": "NASA",
        })
    return out


# เรียงตามโอกาสได้ "ภาพถ่ายที่ดูดีบนคลิปสั้น" ไม่ใช่ตามขนาดคลัง
# Commons ใหญ่กว่ามากแต่เก็บทุกอย่างปนกัน ค้นคำว่า ocean current แล้วได้
# แผนผังลูกศรกับแผนที่ปี 1943 มาก่อนภาพทะเลจริง ซึ่งคนเลื่อนผ่านทันที
# Openverse รวมภาพถ่ายจาก Flickr และพิพิธภัณฑ์ไว้ จึงได้ภาพถ่ายจริงบ่อยกว่า
# (ทดสอบแล้วยิงติดกันแปดครั้งไม่โดนจำกัดอัตรา)
SOURCES = (("openverse", _openverse), ("wikimedia", _wikimedia), ("nasa", _nasa))


# ---------- จัดภาพให้เป็นจอตั้ง ----------

def compose(src, out_path, width: int, height: int) -> None:
    """ภาพในคลังเกือบทั้งหมดเป็นแนวนอน ต้องแปลงเป็นจอตั้งก่อนใช้

    ครอปตรง ๆ จะตัดสิ่งที่ต้องการให้เห็นหายไปครึ่งหนึ่ง จึงใช้วิธีที่ช่องจริงใช้กัน
    คือเอาภาพเดิมขยายเต็มจอแล้วเบลอหนักเป็นพื้นหลัง แล้ววางภาพคมชัดเต็มความกว้างทับ
    ได้ทั้งเห็นภาพครบและไม่มีแถบดำ
    """
    # ภาพพาโนรามากว้าง ๆ ถ้าวางเต็มความกว้างเฉย ๆ จะเหลือเป็นแถบบางกลางจอ
    # ล้อมด้วยพื้นเบลอเรียบ ๆ ที่กินพื้นที่เกือบทั้งคลิป ตัดให้ไม่กว้างเกิน 4:3 ก่อน
    # ภาพจะได้สูงพอจนเป็นพระเอกของเฟรม ไม่ใช่ของประดับกลางพื้นเทา
    vf = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=46:3,eq=brightness=-0.26:saturation=1.25,"
        # ขอบมืดลงรอบนอกทำให้สายตาวิ่งเข้ากลางเอง และกลบความแบนของพื้นหลังที่เบลอแล้ว
        f"vignette=PI/4[bg];"
        f"[0:v]crop=w='min(iw,ih*4/3)':h='min(ih,iw*4/3)',"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-filter_complex", vf,
         "-frames:v", "1", "-q:v", "2", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("จัดภาพไม่สำเร็จ:\n" + result.stderr[-400:])


def _variants(query: str) -> list[str]:
    """ไล่ผ่อนคำค้นลงทีละขั้นเมื่อของเดิมไม่เจอ

    AI ชอบเขียนคำค้นที่เฉพาะเกินจนไม่มีภาพไหนในโลกตรงทั้งวลี
    เช่น "European eel underwater" ได้ศูนย์ผล แต่ "European eel" ได้สิบเอ็ด
    ตัดคำท้ายทิ้งทีละคำจึงได้คำที่กว้างขึ้นแต่ยังเป็นเรื่องเดียวกัน
    """
    words = query.split()
    out = [query]
    for cut in range(1, len(words)):
        shorter = " ".join(words[:-cut])
        if len(shorter) > 2:
            out.append(shorter)
    return out


def fetch(query: str, out_path, cfg: dict, used: set[str] | None = None) -> dict:
    """หาภาพของฉากหนึ่ง คืนข้อมูลเครดิตที่ต้องเอาไปใส่คำอธิบายคลิป

    used เก็บ url ที่ใช้ไปแล้วในคลิปนี้ กันไม่ให้ได้ภาพเดียวกันสองฉาก
    ซึ่งเกิดบ่อยเพราะคำค้นของฉากใกล้เคียงกันมักให้ผลลัพธ์ชุดเดียวกัน
    """
    used = used if used is not None else set()
    width = cfg["images"].get("width") or cfg["video"]["width"]
    height = cfg["images"].get("height") or cfg["video"]["height"]
    allowed = cfg["images"].get("stock_sources") or [name for name, _ in SOURCES]
    problems = []

    def _grab(hit) -> bool:
        try:
            raw = requests.get(hit["url"], timeout=TIMEOUT, headers={"User-Agent": UA})
            raw.raise_for_status()
            tmp = out_path.with_suffix(".src")
            tmp.write_bytes(raw.content)
            compose(tmp, out_path, width, height)
            tmp.unlink(missing_ok=True)
            return True
        except Exception as exc:  # noqa: BLE001 - ภาพเสียก็ลองใบถัดไป
            problems.append(f"{hit['title'][:20]}: {type(exc).__name__}")
            return False

    spare = None   # ภาพที่เคยใช้ไปแล้วในคลิปนี้ เก็บไว้เป็นทางสุดท้าย

    for term in _variants(query):
        for name, search in SOURCES:
            if name not in allowed:
                continue
            try:
                hits = [h for h in search(term) if h["url"]]
            except Exception as exc:  # noqa: BLE001 - คลังล่มไม่ควรทำให้ทั้งคลิปพัง
                problems.append(f"{name}: {type(exc).__name__}")
                continue

            photos = [h for h in hits if _looks_like_photo(h["title"])]
            # ถ้าคัดจนไม่เหลืออะไรเลย ยอมใช้ของเดิมดีกว่าไม่มีภาพ
            hits = sorted(photos or hits, key=lambda h: -_score(h, term))

            fresh = [h for h in hits if h["url"] not in used]
            spare = spare or next(iter(hits), None)

            for hit in fresh[:4]:
                if _grab(hit):
                    used.add(hit["url"])
                    return hit

    # ภาพซ้ำในคลิปเดียวกันไม่สวย แต่ยังดีกว่าทิ้งคลิปทั้งคลิปเพราะฉากเดียว
    if spare and _grab(spare):
        return spare

    raise RuntimeError(f"หาภาพสำหรับ '{query}' ไม่ได้ — {'; '.join(problems[:4])}")


def credit_lines(credits: list[dict]) -> str:
    """รวมเครดิตเป็นข้อความสำหรับท้ายคำอธิบายคลิป ตัดใบที่ซ้ำกันออก"""
    seen, lines = set(), []
    for c in credits:
        key = (c["title"], c["author"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• {c['title']} — {c['author']} ({c['license']}) {c['source']}".strip())
    return "ที่มาของภาพ:\n" + "\n".join(lines) if lines else ""
