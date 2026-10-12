"""แปลงจังหวะคำจาก edge-tts เป็นไฟล์ซับ .ass"""

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},{primary},{outline_colour},&H64000000,1,0,1,{outline},2,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text
"""


def _timestamp(seconds: float) -> str:
    seconds = max(seconds, 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


PAUSE_GAP = 0.22        # ช่องว่างระหว่างคำที่ถือว่าเป็นการเว้นวรรค
OVERFLOW_SLACK = 1.2    # ยอมให้บรรทัดยาวเกินเพดานได้กี่เท่า ก่อนตัดสินใจหักบรรทัด


def _as_line(words: list[dict]) -> dict:
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": "".join(w["text"] for w in words).strip(),
    }


def _space_starts(words: list[dict], source: str) -> set[int]:
    """หาว่าคำไหนอยู่หลังช่องว่างในบทต้นฉบับ

    TTS ไทยเว้นจังหวะสั้นมากจนวัดจากเวลาไม่ค่อยได้ผล แต่ช่องว่างที่คนเขียนใส่ไว้
    คือตำแหน่งแบ่งวรรคที่ตั้งใจจริง ๆ เลยใช้อันนั้นเป็นหลัก
    """
    starts: set[int] = set()
    cursor = 0
    for index, word in enumerate(words):
        found = source.find(word["text"], cursor)
        if found == -1:
            continue
        if found > 0 and source[found - 1].isspace():
            starts.add(index)
        cursor = found + len(word["text"])
    return starts


def _split_into_phrases(words: list[dict], source: str | None = None) -> list[list[dict]]:
    """ตัดเป็นวรรคตามช่องว่างในบท และตามจังหวะที่คนพากย์หยุด"""
    breaks = _space_starts(words, source) if source else set()

    phrases: list[list[dict]] = []
    current: list[dict] = []
    for index, word in enumerate(words):
        gap = word["start"] - current[-1]["end"] if current else 0.0
        if current and (index in breaks or gap >= PAUSE_GAP):
            phrases.append(current)
            current = []
        current.append(word)
    if current:
        phrases.append(current)
    return phrases


def _wrap_phrase(phrase: list[dict], max_chars: int) -> list[list[dict]]:
    """ซอยวรรคยาวให้พอดีจอ โดยเกลี่ยให้ทุกบรรทัดยาวใกล้เคียงกัน

    ถ้าไล่เติมจนเต็ม max_chars ไปเรื่อย ๆ บรรทัดสุดท้ายมักเหลือคำเดียวโดด ๆ
    การหารความยาวรวมด้วยจำนวนบรรทัดก่อนแล้วค่อยเติมทำให้ไม่มีเศษแบบนั้น
    """
    total = sum(len(w["text"]) for w in phrase)
    # ยอมให้ล้นได้เล็กน้อย ดีกว่าหักวรรคสั้น ๆ ออกเป็นสองบรรทัดครึ่ง ๆ กลาง ๆ
    if total <= max_chars * OVERFLOW_SLACK:
        return [phrase]

    line_count = -(-total // max_chars)  # ปัดขึ้น
    target = total / line_count

    chunks: list[list[dict]] = []
    current: list[dict] = []
    length = 0
    for word in phrase:
        remaining = line_count - len(chunks)
        # กันไม่ให้บรรทัดท้าย ๆ ว่างเปล่าเมื่อคำที่เหลือน้อยกว่าจำนวนบรรทัด
        if current and length >= target and remaining > 1 and len(phrase) - len(current) > 0:
            chunks.append(current)
            current, length = [], 0
        current.append(word)
        length += len(word["text"])
    if current:
        chunks.append(current)
    return chunks


def group_words(words: list[dict], max_chars: int, source: str | None = None) -> list[dict]:
    """รวมคำเป็นบรรทัดซับ

    ภาษาไทยเขียนติดกันไม่มีช่องว่าง การตัดตามวรรคและจังหวะพูดจึงอ่านง่ายกว่านับตัวอักษรล้วน ๆ
    ส่ง source เป็นบทต้นฉบับเข้ามาด้วยจะได้ผลดีที่สุด
    """
    lines: list[dict] = []
    for phrase in _split_into_phrases(words, source):
        for chunk in _wrap_phrase(phrase, max_chars):
            if chunk:
                lines.append(_as_line(chunk))
    return [line for line in lines if line["text"]]


# ---------- โหมดสำรอง: มีแค่เวลาเริ่มจบของทั้งวรรค ----------

def _words(text: str) -> list[str]:
    """แบ่งข้อความไทยเป็นคำ

    ภาษาไทยไม่มีช่องว่างระหว่างคำ การเดาจุดตัดจากจำนวนตัวอักษรจึงตัดกลางคำ
    ได้ง่ายมาก เคยได้ "ไม่อ" ท้ายบรรทัดแล้ว "ยู่" ขึ้นบรรทัดใหม่ ซึ่งอ่านสะดุด

    pythainlp รู้ขอบเขตคำจริง ถ้าไม่มีก็ถอยไปซอยตามตัวอักษรแทน
    เพราะซับที่ตัดคำไม่สวยยังดีกว่าคลิปที่ไม่มีซับ
    """
    try:
        from pythainlp.tokenize import word_tokenize
    except ImportError:
        return [text[i:i + 6] for i in range(0, len(text), 6)]

    # ช่องว่างในบทคือจังหวะหยุดที่คนเขียนตั้งใจไว้ ทิ้งไปแล้วประโยคจะติดกันหมด
    # เอาไปต่อท้ายคำก่อนหน้าแทน จะได้ยังเป็นจุดตัดบรรทัดที่ดีอยู่
    out: list[str] = []
    for token in word_tokenize(text, engine="newmm"):
        if token.strip():
            out.append(token)
        elif out:
            out[-1] += " "
    return out


def _chunks(text: str, max_chars: int) -> list[str]:
    """ซอยข้อความให้พอดีจอ โดยเกลี่ยให้ทุกบรรทัดยาวใกล้เคียงกัน

    คำนวณจำนวนบรรทัดก่อนแล้วค่อยเกลี่ย ไม่ใช่เติมจนเต็มแล้วขึ้นบรรทัดใหม่
    เพราะวิธีหลังทำให้บรรทัดสุดท้ายเหลือคำเดียวโดด ๆ อยู่ไม่ถึงครึ่งวินาที
    """
    text = text.strip()
    if len(text) <= max_chars * OVERFLOW_SLACK:
        return [text]

    words = _words(text)
    count = max(1, min(-(-len(text) // max_chars), len(words)))

    lines, rest = [], list(words)
    for remaining in range(count, 0, -1):
        if remaining == 1:
            lines.append("".join(rest))
            break
        target = sum(len(w) for w in rest) / remaining
        taken, length = [], 0
        while rest and (not taken or length + len(rest[0]) / 2 <= target):
            taken.append(rest.pop(0))
            length += len(taken[-1])
        lines.append("".join(taken))
    return [line.strip() for line in lines if line.strip()]


def from_phrases(segments: list[dict], max_chars: int) -> list[dict]:
    """ทำบรรทัดซับจากวรรคที่รู้แค่เวลาเริ่มกับจบ

    ตัวพากย์สำรองไม่บอกจังหวะรายคำ ให้มาแค่ว่าแต่ละวรรคเริ่มและจบเมื่อไหร่
    ถ้าเอาทั้งวรรคเป็นบรรทัดเดียวจะยาวล้นจอเวลาวรรคนั้นยาว

    จึงซอยเป็นบรรทัดแล้วเกลี่ยเวลาตามจำนวนตัวอักษร ซึ่งเป็นการประมาณ
    แต่แม่นพอ เพราะวรรคหนึ่งยาวแค่ไม่กี่วินาทีและคนพูดด้วยจังหวะใกล้เคียงกัน
    ภายในวรรคเดียว คลาดเคลื่อนระดับเศษส่วนวินาทีซึ่งตาไม่ทันอยู่แล้ว
    """
    lines: list[dict] = []
    for seg in segments:
        pieces = _chunks(seg["text"], max_chars)
        total = sum(len(p) for p in pieces) or 1
        span = seg["end"] - seg["start"]
        at = seg["start"]
        for piece in pieces:
            width = span * len(piece) / total
            lines.append({"text": piece, "start": at, "end": at + width})
            at += width
    return [line for line in lines if line["text"]]


def write_ass(lines: list[dict], out_path, cfg: dict) -> None:
    sub = cfg["subtitles"]
    body = HEADER.format(
        width=cfg["video"]["width"],
        height=cfg["video"]["height"],
        font=sub["font"],
        size=sub["font_size"],
        primary=sub["primary_color"],
        outline_colour=sub["outline_color"],
        outline=sub["outline"],
        margin_v=sub["margin_v"],
    )

    events = []
    for index, line in enumerate(lines):
        # กันซับบรรทัดถัดไปทับบรรทัดก่อนหน้าเวลาช่องว่างระหว่างคำสั้นมาก
        end = line["end"]
        if index + 1 < len(lines):
            end = min(end + 0.25, lines[index + 1]["start"])
        end = max(end, line["start"] + 0.3)
        text = line["text"].replace("\n", " ")
        # ลำดับ field ต้องตรงกับ Format: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text
        # ใส่เกินมาหนึ่งช่องเมื่อไหร่ ค่าที่เกินจะไหลไปโผล่เป็นตัวอักษรหน้าซับ
        events.append(
            f"Dialogue: 0,{_timestamp(line['start'])},{_timestamp(end)},Main,,0,0,,{text}"
        )

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body + "\n".join(events) + "\n")
