"""ทำปกคลิปจากภาพฉากฮุก พร้อมข้อความใหญ่

จุดที่ต้องระวัง: FFmpeg drawtext วาดภาษาไทยผิด เพราะมันวางตัวอักษรเรียงกันตรง ๆ
ไม่รู้จักการจัดวางสระบนล่างและวรรณยุกต์ (ไม่มี text shaping)
จึงเลี่ยงไปใช้ตัวเดียวกับที่ทำซับในคลิป คือ libass ผ่าน filter subtitles
ซึ่งพิสูจน์แล้วว่าวางสระไทยถูกต้อง

วิธีคือทำคลิปหนึ่งเฟรมจากภาพ เบิร์นข้อความลงไป แล้วดึงเฟรมนั้นออกมาเป็นไฟล์ภาพ
"""
import subprocess
from pathlib import Path

from ..config import ASSETS

THUMB_W, THUMB_H = 720, 1280   # 9:16 ให้ตรงกับที่ Shorts แสดงในหน้าช่อง

ASS_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cover,{font},{size},&H00FFFFFF,&H00202020,&H90000000,1,0,1,7,3,2,50,50,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Cover,,0,0,,{text}
"""


# สระและวรรณยุกต์ไทยที่เกาะอยู่กับพยัญชนะตัวหน้า ตัดบรรทัดคั่นกลางไม่ได้
# ไม่งั้นจะได้ "ก" ท้ายบรรทัดหนึ่ง แล้วไม้โทลอยขึ้นต้นอีกบรรทัด
THAI_COMBINING = (
    "ั"                                    # ไม้หันอากาศ
    "ิีึืฺุู"  # สระบน-ล่าง
    "็่้๊๋์ํ๎"  # วรรณยุกต์และการันต์
)


def _safe_cut(word: str, at: int) -> int:
    """เลื่อนจุดตัดถอยหลังจนไม่ได้ตัดคั่นระหว่างพยัญชนะกับสระที่เกาะอยู่"""
    while at > 1 and word[at] in THAI_COMBINING:
        at -= 1
    return at


def _wrap(text: str, per_line: int = 12) -> str:
    """ตัดบรรทัดให้ตัวอักษรใหญ่ได้ ไม่ใช่บรรทัดเดียวยาวจนล้นจอ

    ตัดตามช่องว่างก่อนถ้ามี แต่ภาษาไทยไม่มีช่องว่างระหว่างคำ ประโยคทั้งประโยค
    จึงนับเป็นคำเดียวและไม่เคยถูกตัด ต้องมีตัวตัดตามจำนวนตัวอักษรคอยรับด้วย
    """
    lines: list[str] = []
    current = ""

    for word in (text.split() or [text]):
        # คำเดียวที่ยาวเกินบรรทัด (เช่นภาษาไทยทั้งประโยค) ต้องซอยตามตัวอักษร
        while len(word) > per_line:
            if current:
                lines.append(current)
                current = ""
            cut = _safe_cut(word, per_line)
            lines.append(word[:cut])
            word = word[cut:]

        candidate = f"{current} {word}".strip()
        if current and len(candidate) > per_line:
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)
    return "\\N".join(lines[:3])   # \\N คือขึ้นบรรทัดใหม่ในรูปแบบ ASS


def make(image: Path, text: str, out_path: Path, work: Path) -> Path:
    """สร้างปกจากภาพหนึ่งใบ + ข้อความ คืน path ของไฟล์ปก"""
    work.mkdir(parents=True, exist_ok=True)
    ass_path = work / "cover.ass"

    # ข้อความยาวต้องใช้ตัวเล็กลง ไม่งั้นล้นออกนอกจอ
    length = len(text)
    size = 122 if length <= 14 else (100 if length <= 24 else 80)

    ass_path.write_text(
        ASS_TEMPLATE.format(w=THUMB_W, h=THUMB_H, font="Noto Sans Thai",
                            size=size, margin=200, text=_wrap(text)),
        encoding="utf-8",
    )

    subs = ass_path.as_posix().replace("\\", "/").replace(":", r"\:")
    fonts = (ASSETS / "fonts").as_posix().replace("\\", "/").replace(":", r"\:")

    vf = (
        f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,"
        f"crop={THUMB_W}:{THUMB_H},"
        # ไล่เฉดมืดจากล่างขึ้นบน ให้ตัวหนังสือขาวอ่านออกไม่ว่าพื้นหลังจะสว่างแค่ไหน
        # ใช้แถบบาง ๆ ซ้อนกันหลายชั้นแทนไล่เฉดจริง เพราะ geq ช้ากว่ามาก
        # แถบหนา ๆ ไม่กี่ชั้นจะเห็นขอบเป็นชั้น ๆ ชัดเจน ต้องซอยให้ถี่พอ
        + "".join(
            f"drawbox=x=0:y=ih*{0.50 + i * 0.05:.2f}:w=iw:h=ih*0.06:"
            f"color=black@{0.06 + i * 0.065:.3f}:t=fill,"
            for i in range(10)
        ) +
        f"subtitles='{subs}':fontsdir='{fonts}'"
    )

    result = subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(image), "-frames:v", "1",
         "-vf", vf, "-q:v", "2", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("สร้างปกไม่สำเร็จ:\n" + result.stderr[-400:])
    return out_path
