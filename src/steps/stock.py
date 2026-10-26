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
import time
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


# ภาพถ่ายจริงแต่หลุดธีมสิ้นเชิง เพราะคำค้นไปตรงกับ "ชื่อบริษัท" แทนที่จะเป็นของจริง
# เคสที่เจอ: ค้น arctic glacier ice แล้วได้ตึกออฟฟิศของบริษัทขายน้ำแข็งในวินนิเพก
# ซึ่งได้คะแนนสูงสุดเพราะมีครบทั้งสามคำในชื่อ ตัวกรองภาพถ่ายจับไม่ได้เพราะมันเป็นภาพถ่ายจริง
CORPORATE = (
    "headquarters", "corporate", "office building", "warehouse", "storefront",
    "inc.", "ltd", "llc", "company building", "factory outlet", "dealership",
    "shopping", "mall", "supermarket", "billboard", "advertisement",
)


def _score(hit: dict, query: str) -> int:
    """ยิ่งคำในคำค้นโผล่ในชื่อไฟล์มาก ยิ่งน่าจะเป็นภาพที่ตรงเรื่องจริง

    ไม่ใช่การวัดที่แม่น แต่ดีกว่าเชื่อลำดับที่คลังส่งมา ซึ่งเรียงตามความ
    เกี่ยวข้องของข้อความทั้งหน้า ไม่ใช่ความเกี่ยวข้องของตัวภาพ
    """
    low = hit["title"].lower()
    hits = sum(1 for word in query.lower().split() if len(word) > 2 and word in low)
    # หักแรงพอให้ตกไปอยู่ท้ายแถวเสมอ แต่ไม่ตัดทิ้ง เผื่อว่าไม่มีอย่างอื่นเลยจริง ๆ
    return hits - (9 if any(w in low for w in CORPORATE) else 0)


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
            # Commons ใช้ขนาดภาพย่อมาตรฐานชุดหนึ่ง เปลี่ยนตัวเลขในลิงก์เป็น 500 ได้ภาพเล็กพอให้ AI ดู
            # เดิมแทนเฉพาะ "1600px" แต่ลิงก์จริงใช้ขนาดอื่น เลยได้ไฟล์เต็มขนาดหลาย MB มาแทน
            "thumb": re.sub(r"/\d+px-", "/500px-", info.get("thumburl") or "") or None,
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
            "thumb": item.get("thumbnail"),
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
            "thumb": links[0].get("href"),
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


# ---------- ให้ AI ดูภาพจริงก่อนเลือก ----------

VISION_PROMPT = """You are the photo editor of a factual YouTube Shorts channel.

STORY (the truth you must match): {context}
Search words used for this scene: {query}

Below are {n} candidate photos, numbered 0 to {last} in order.
Pick the ONE photo that a viewer would accept as a real photo of THIS STORY's subject and place.

Judge against the STORY, not the search words. The search words can be wrong or too broad.
If the story says something is NOT X, a photo of X is wrong even if the search words mention X.

Reject a photo if it is any of these:
- a different subject, place, animal or object than the story (a whale in a story about a forest,
  a volcano in Iceland in a story about a river in the Amazon, a zoo exhibit instead of the real place)
- a diagram, simulation, satellite false-colour image, map, chart, illustration, painting, engraving,
  cartoon, collage or screenshot
- mostly text, a logo, or people posing unrelated to the subject

- a look-alike: a different mountain, river or forest that only looks similar.
  If the story names a specific place or thing, the photo must BE that place or thing.
  Use each photo's title (listed below) to check what it really is.

Photo titles:
{titles}

If none of them clearly fits, answer best = -1. A wrong photo is worse than no photo.
Give a short reason in English."""

VISION_SCHEMA = {
    "type": "object",
    "properties": {"best": {"type": "integer"}, "reason": {"type": "string"}},
    "required": ["best"],
}


def _vision_pick(cands: list[dict], query: str, context: str, cfg: dict) -> int:
    """ส่งภาพตัวเลือกให้ Gemini ดู แล้วคืนลำดับภาพที่ตรงเรื่องที่สุด หรือ -1 ถ้าไม่มี

    การค้นด้วยคำอย่างเดียวคืนภาพที่ "คำตรง" แต่ "ภาพผิด" บ่อยมาก
    เช่นค้นสิ่งมีชีวิตที่ใหญ่ที่สุดแล้วได้หางวาฬมาใส่คลิปเรื่องป่า
    หรือเรื่องแม่น้ำเดือดที่ไม่ได้เกิดจากภูเขาไฟ กลับได้ภาพภูเขาไฟในไอซ์แลนด์
    ถ้าเรียก AI ไม่ได้จะโยน error ให้คนเรียกตัดสินใจเอง ไม่แอบเลือกมั่ว ๆ แทน
    """
    import base64
    import json
    from ..config import secret

    parts, kept = [], []
    for c in cands:
        url = c.get("thumb") or c["url"]
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": UA})
            r.raise_for_status()
        except Exception:  # noqa: BLE001 - โหลดภาพตัวอย่างไม่ได้ก็ตัดตัวนี้ทิ้ง
            continue
        mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0]
        if not mime.startswith("image/") or len(r.content) > 1_500_000:
            continue
        kept.append(c)
        parts.append({"inline_data": {"mime_type": mime,
                                      "data": base64.b64encode(r.content).decode()}})
    if not kept:
        return -1

    titles = "\n".join(f"{i}: {c['title'][:90]}" for i, c in enumerate(kept))
    prompt = VISION_PROMPT.format(context=context or query, query=query, titles=titles,
                                  n=len(kept), last=len(kept) - 1)
    body = {"contents": [{"parts": [{"text": prompt}, *parts]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "responseSchema": VISION_SCHEMA}}
    last = None
    # รุ่นเล็กตอบใน 4-5 วินาที รุ่นใหญ่ 8-11 วินาที แต่ดูภาพว่าตรงเรื่องไหมได้พอกัน
    models = (cfg.get("images") or {}).get("vision_models") or         ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash"]
    for model in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": secret("GEMINI_API_KEY")}, json=body, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"{model} {r.status_code}"
                print(f"      ตรวจภาพด้วย {model} ไม่ได้ ({r.status_code}) ลองรุ่นถัดไป")
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            answer = json.loads(text)
            best = int(answer.get("best", -1))
            reason = str(answer.get("reason", ""))[:110]
            if 0 <= best < len(kept):
                print(f"      AI เลือกภาพ: {kept[best]['title'][:50]} — {reason}")
                # คืนลำดับในรายการเดิม ไม่ใช่ในรายการที่ตัดตัวโหลดไม่ได้ทิ้งไปแล้ว
                return cands.index(kept[best])
            print(f"      AI ไม่รับภาพชุด '{query}' — {reason}")
            return -1
        except Exception as exc:  # noqa: BLE001 - ลองรุ่นถัดไป
            last = f"{model} {type(exc).__name__}: {str(exc)[:80]}"
            print(f"      ตรวจภาพด้วย {model} ไม่ได้ ({last})")
    raise RuntimeError(f"ตรวจภาพด้วย AI ไม่ได้: {last}")


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


def fetch(query: str, out_path, cfg: dict, used: set[str] | None = None,
          context: str = "", approved: list[dict] | None = None, subject: str = "") -> dict:
    """หาภาพของฉากหนึ่ง คืนข้อมูลเครดิตที่ต้องเอาไปใส่คำอธิบายคลิป

    used เก็บ url ที่ใช้ไปแล้วในคลิปนี้ กันไม่ให้ได้ภาพเดียวกันสองฉาก
    context คือชื่อเรื่องกับบทของฉาก ให้ AI รู้ว่าภาพต้องเกี่ยวกับอะไร
    approved เก็บภาพที่ AI รับรองแล้วในคลิปนี้ ใช้ซ้ำได้เมื่อฉากไหนหาภาพที่ตรงไม่เจอ
    เพราะภาพซ้ำหนึ่งฉากยังดีกว่าภาพผิดเรื่อง ซึ่งคนดูเห็นแล้วเสียความเชื่อถือทันที
    subject คือคำค้นของหัวเรื่องหลักทั้งคลิป เช่น "Pando aspen clone"
    ใช้ค้นสำรองเมื่อคำค้นของฉากกว้างเกินจนไม่มีภาพตรง ซึ่งภาพของหัวเรื่องหลักมีแน่นอน
    """
    used = used if used is not None else set()
    approved = approved if approved is not None else []
    width = cfg["images"].get("width") or cfg["video"]["width"]
    height = cfg["images"].get("height") or cfg["video"]["height"]
    allowed = cfg["images"].get("stock_sources") or [name for name, _ in SOURCES]
    use_vision = cfg["images"].get("vision_check", True)
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

    def _first_ok(cands):
        for hit in cands[:4]:
            if _grab(hit):
                used.add(hit["url"])
                return hit
        return None

    first_unchecked = None   # ใช้เฉพาะเมื่อไม่มีภาพไหนผ่านเลยในฉากแรกของคลิป

    terms = _variants(query)
    if subject and subject.lower() not in [t.lower() for t in terms]:
        terms.insert(1, subject)
    vision_answered = False   # AI ตอบได้อย่างน้อยหนึ่งครั้ง แปลว่าภาพที่ไม่ผ่านคือภาพที่ถูกปฏิเสธจริง

    for term in terms:
        # รวมผลจากทุกคลังก่อนแล้วค่อยให้ AI เลือก ไม่หยุดที่คลังแรกที่เจออะไรก็ได้
        pool = []
        for name, search in SOURCES:
            if name not in allowed:
                continue
            try:
                hits = [h for h in search(term) if h["url"]]
            except Exception as exc:  # noqa: BLE001 - คลังล่มไม่ควรทำให้ทั้งคลิปพัง
                problems.append(f"{name}: {type(exc).__name__}")
                continue
            photos = [h for h in hits if _looks_like_photo(h["title"])]
            pool += sorted(photos or hits, key=lambda h: -_score(h, term))[:4]

        seen, fresh = set(), []
        for h in pool:
            if h["url"] in used or h["url"] in seen:
                continue
            seen.add(h["url"])
            fresh.append(h)
        fresh = fresh[:6]
        if not fresh:
            continue
        first_unchecked = first_unchecked or fresh[0]

        if not use_vision:
            hit = _first_ok(fresh)
            if hit:
                return hit
            continue

        try:
            try:
                pick = _vision_pick(fresh, term, context, cfg)
            except RuntimeError:
                # ส่วนใหญ่คือโควตาต่อนาทีเต็ม รอสักพักแล้วลองอีกครั้งก่อนยอมแพ้
                time.sleep(30)
                pick = _vision_pick(fresh, term, context, cfg)
        except RuntimeError as exc:
            if vision_answered:
                # AI เคยตอบในฉากนี้แล้ว ภาพที่เหลือคือภาพที่ยังไม่ผ่าน ไม่หยิบมาใช้มั่ว ๆ
                problems.append(str(exc))
                if subject and term == subject and terms.count(subject) < 2:
                    terms.append(subject)   # หัวเรื่องหลักสำคัญที่สุด ลองใหม่ตอนท้ายอีกรอบ
                continue
            # AI ล่มทั้งรอบ ถอยไปใช้วิธีเลือกจากคะแนนคำค้นแทนการหยุดทั้งคลิป
            problems.append(str(exc))
            print(f"      เตือน: {exc} — เลือกภาพจากคะแนนคำค้นแทน")
            use_vision = False
            hit = _first_ok(fresh)
            if hit:
                return hit
            continue

        vision_answered = True
        if pick >= 0 and _grab(fresh[pick]):
            hit = fresh[pick]
            used.add(hit["url"])
            approved.append(hit)
            return hit
        problems.append(f"'{term}': ไม่มีภาพที่ตรงเรื่อง")

    # ไม่เจอภาพที่ตรงเรื่องเลย ใช้ภาพที่รับรองแล้วจากฉากก่อนซ้ำ ดีกว่าใส่ภาพผิด
    for hit in reversed(approved):
        if _grab(hit):
            print("      ฉากนี้หาภาพที่ตรงไม่เจอ ใช้ภาพของฉากก่อนซ้ำ")
            return hit

    # ถ้า AI ตรวจแล้วปฏิเสธทุกภาพ ห้ามหยิบภาพพวกนั้นมาใช้ เพราะมันคือภาพที่ "รู้แล้ว" ว่าผิดเรื่อง
    # ใช้ฉากพื้นหลังเรียบแทน ซึ่งไม่ทำให้คนดูเข้าใจผิด
    if vision_answered:
        _plain_card(out_path, width, height)
        print(f"      ไม่มีภาพที่ตรงเรื่องสำหรับ '{query}' ใช้ฉากพื้นหลังเรียบแทน")
        return {"url": "", "title": "", "author": "", "license": "", "source": "", "via": "card"}

    # AI ใช้ไม่ได้เลยทั้งรอบ ถอยไปใช้ภาพที่คะแนนคำค้นดีที่สุด ดีกว่าหยุดทั้งคลิป
    if first_unchecked and _grab(first_unchecked):
        print(f"      เตือน: ตรวจภาพไม่ได้ ใช้ภาพจากคะแนนคำค้นสำหรับ '{query}'")
        return first_unchecked

    raise RuntimeError(f"หาภาพสำหรับ '{query}' ไม่ได้ — {'; '.join(problems[:4])}")


def _plain_card(out_path, width: int, height: int) -> None:
    """ฉากพื้นหลังเรียบโทนเดียวกับช่อง ใช้แทนภาพเมื่อหาภาพที่ตรงเรื่องไม่ได้จริง ๆ"""
    vf = (f"color=c=0x0b1424:s={width}x{height},"
          f"geq=r='11+30*exp(-((X-{width}*0.3)^2+(Y-{height}*0.35)^2)/(2*({width}*0.35)^2))':"
          f"g='20+60*exp(-((X-{width}*0.3)^2+(Y-{height}*0.35)^2)/(2*({width}*0.35)^2))':"
          f"b='36+70*exp(-((X-{width}*0.7)^2+(Y-{height}*0.7)^2)/(2*({width}*0.4)^2))'")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf, "-frames:v", "1", "-q:v", "3", str(out_path)],
                   capture_output=True, check=True)


def credit_lines(credits: list[dict]) -> str:
    """รวมเครดิตเป็นข้อความสำหรับท้ายคำอธิบายคลิป ตัดใบที่ซ้ำกันออก"""
    seen, lines = set(), []
    for c in credits:
        if not c.get("url"):
            continue
        key = (c["title"], c["author"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• {c['title']} — {c['author']} ({c['license']}) {c['source']}".strip())
    return "ที่มาของภาพ:\n" + "\n".join(lines) if lines else ""
