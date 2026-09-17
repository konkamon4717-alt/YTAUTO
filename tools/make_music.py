"""สังเคราะห์เสียงคลอพื้นหลังด้วย FFmpeg

ทำไมต้องสังเคราะห์เอง: เพลงฟรีที่หาได้ส่วนใหญ่เป็น CC-BY-NC ซึ่ง "ห้ามใช้เชิงพาณิชย์"
จึงใช้กับช่องหารายได้ไม่ได้ ส่วน CC-BY ใช้ได้แต่ต้องให้เครดิตและยังเสี่ยงโดน Content ID
ถ้าผู้อัปโหลดต้นทางติดป้ายลิขสิทธิ์ไว้ผิด เสียงที่เราสร้างเองไม่มีความเสี่ยงนั้นเลย
และเป็นของช่องเราคนเดียว ซึ่งช่วยเรื่องเอกลักษณ์ด้วย

เสียงที่ได้เป็น pad เรียบ ๆ ไม่มีทำนอง ตั้งใจให้เป็นพื้นหลังที่ไม่แย่งความสนใจ
จากเสียงพากย์ เปิดคลอที่ระดับต่ำมากใต้เสียงเล่าเรื่อง

  python tools/make_music.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "music"
SECONDS = 90          # ยาวกว่าคลิปเสมอ จะได้ไม่ต้องวนซ้ำให้ได้ยินรอยต่อ

# คอร์ดของแต่ละชุด — เลือกโทนที่เข้ากับนิทานก่อนนอน ไม่หวือหวา
BEDS = {
    # Am9 นุ่ม ๆ โทนอบอุ่น ใช้กับเรื่องทั่วไป
    "warm_am9":   [110.00, 164.81, 261.63, 329.63, 493.88],
    # Fmaj7 สว่างขึ้นนิด ใช้กับเรื่องจบแบบมีความหวัง
    "bright_fmaj7": [87.31, 174.61, 261.63, 349.23, 440.00],
    # Dm โทนเศร้าเล็กน้อย ใช้กับเรื่องที่มีบทเรียนหนัก
    "soft_dm":    [73.42, 146.83, 220.00, 293.66, 440.00],
}


def build(name: str, freqs: list[float]) -> Path:
    inputs = []
    for f in freqs:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={SECONDS}"]

    # ผสมทุกเสียงเข้าด้วยกันแล้วทำให้ "หายใจ" ช้า ๆ ไม่ให้นิ่งจนน่าเบื่อ
    # lowpass ตัดความแหลมออก เสียงจะไม่บาดหูและไม่ชนกับเสียงพูด
    # aecho เพิ่มความกว้างให้ฟังเหมือนอยู่ในห้อง ไม่ใช่เสียงสังเคราะห์แห้ง ๆ
    chain = (
        f"amix=inputs={len(freqs)}:duration=longest:normalize=1,"
        "tremolo=f=0.12:d=0.35,"
        "lowpass=f=900,"
        "aecho=0.8:0.85:320|580:0.28|0.2,"
        "volume=0.9,"
        f"afade=t=in:st=0:d=4,afade=t=out:st={SECONDS - 5}:d=5"
    )

    out = OUT / f"{name}.mp3"
    result = subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", chain,
         "-ac", "2", "-ar", "44100", "-b:a", "128k", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"สร้าง {name} ไม่สำเร็จ:\n" + result.stderr[-400:])
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, freqs in BEDS.items():
        path = build(name, freqs)
        print(f"  {path.name:<20} {path.stat().st_size / 1000:>5.0f} KB")
    print(f"\nสร้างเสร็จ {len(BEDS)} ชุดที่ {OUT}")
    print("ระบบจะสุ่มหยิบมาใช้ 1 ชุดต่อคลิป")
    return 0


if __name__ == "__main__":
    sys.exit(main())
