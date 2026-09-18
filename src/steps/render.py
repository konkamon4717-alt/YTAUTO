"""ประกอบภาพ + เสียง + ซับ เป็นคลิปแนวตั้งด้วย FFmpeg"""
import json
import random
import subprocess
from pathlib import Path

from ..config import ASSETS


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        tail = result.stderr.strip().splitlines()[-25:]
        raise RuntimeError("FFmpeg ล้มเหลว:\n" + "\n".join(tail))


def duration_of(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"อ่านความยาวไฟล์ไม่ได้: {path}")
    return float(json.loads(result.stdout)["format"]["duration"])


# การเคลื่อนกล้องบนภาพนิ่ง สลับไปเรื่อย ๆ ตามลำดับฉาก
# ระยะทางของทุกท่าถูกคิดจาก "จำนวนเฟรมของฉากนั้น" ไม่ใช่อัตราต่อเฟรมคงที่
# ฉากสั้นกับฉากยาวจึงเคลื่อนครบระยะเท่ากัน ไม่ใช่ฉากสั้นแทบไม่ขยับ
CAMERA_MOVES = ("in", "left", "out", "right", "in", "up")

ZOOM_RANGE = 0.30   # ซูมเข้า/ออก 30% ตลอดฉาก
PAN_ZOOM = 1.26     # ซูมค้างไว้เท่านี้ตอนแพน เพื่อให้มีพื้นที่ให้เลื่อน


def ken_burns(image: Path, seconds: float, out_path: Path, cfg: dict,
              move: str = "in") -> None:
    """ทำภาพนิ่งให้ขยับ ใช้เมื่อโมเดลวิดีโอใช้ไม่ได้

    ของเดิมซูม 10% ตลอด 4 วินาทีซึ่งตาแทบจับไม่ได้ และทุกฉากซูมทิศเดียวกัน
    เลยดูเหมือนภาพนิ่งทั้งคลิป ตอนนี้เพิ่มระยะและสลับทิศทุกฉาก
    """
    width, height, fps = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    frames = max(int(seconds * fps), 2)
    last = frames - 1

    if move == "in":
        zoom = f"min(1.0+{ZOOM_RANGE}*on/{last},{1 + ZOOM_RANGE})"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif move == "out":
        zoom = f"max({1 + ZOOM_RANGE}-{ZOOM_RANGE}*on/{last},1.0)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    else:
        zoom = str(PAN_ZOOM)
        span_x, span_y = "(iw-iw/zoom)", "(ih-ih/zoom)"
        centre_x, centre_y = f"{span_x}/2", f"{span_y}/2"
        if move == "left":
            x, y = f"{span_x}*(1-on/{last})", centre_y
        elif move == "right":
            x, y = f"{span_x}*on/{last}", centre_y
        elif move == "up":
            x, y = centre_x, f"{span_y}*(1-on/{last})"
        else:  # down
            x, y = centre_x, f"{span_y}*on/{last}"

    vf = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}'"
        f":d={frames}:s={width}x{height}:fps={fps},setsar=1"
    )

    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-t", f"{seconds:.3f}",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps), str(out_path),
    ])


def conform(clip: Path, seconds: float, out_path: Path, cfg: dict, work: Path) -> None:
    """ปรับคลิปที่ได้จากโมเดลให้พอดีกับผืนผ้าใบและความยาวของฉาก

    โมเดลฟรีคืนมาที่ 480x832 / 16fps / ~3.5 วินาที ซึ่งไม่ตรงกับที่เราต้องการสักอย่าง
    ถ้าสั้นกว่าที่ต้องการจะต่อขาไปขากลับ (boomerang) แล้ววนจนยาวพอ
    วิธีนี้ไม่มีรอยกระตุกตอนวนซ้ำ เพราะเฟรมสุดท้ายของขาไปคือเฟรมแรกของขากลับ
    """
    width, height, fps = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    source = clip

    if duration_of(clip) < seconds - 0.05:
        boomerang = work / f"boom_{clip.stem}.mp4"
        _run([
            "ffmpeg", "-y", "-i", str(clip),
            "-filter_complex", "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[out]",
            "-map", "[out]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(boomerang),
        ])
        source = boomerang

    loops = max(int(seconds // max(duration_of(source), 0.1)) + 1, 1)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},"
        # โมเดลคืนภาพเล็กกว่าผืนผ้าใบมาก ขยายแล้วจะนุ่ม ชาร์ปเบา ๆ กลับมาให้คมพอดู
        f"unsharp=5:5:0.45:5:5:0.0,"
        f"fps={fps},setsar=1"
    )
    _run([
        "ffmpeg", "-y", "-stream_loop", str(loops), "-i", str(source),
        "-t", f"{seconds:.3f}", "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps), str(out_path),
    ])


def _concat_file(paths: list[Path], list_path: Path) -> None:
    # ต้องเป็น path แบบเต็ม เพราะ FFmpeg หาไฟล์ในรายการนี้โดยอิงจากตำแหน่งของ
    # ไฟล์รายการเอง ไม่ใช่จากที่รันคำสั่ง ใส่ path สัมพัทธ์ลงไปมันจะไปหาซ้อนอีกชั้น
    lines = [f"file '{p.resolve().as_posix()}'" for p in paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat(paths: list[Path], out_path: Path, work: Path, reencode: bool = False) -> None:
    list_path = work / f"concat_{out_path.stem}.txt"
    _concat_file(paths, list_path)
    args = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]
    args += ["-c", "copy"] if not reencode else ["-c:a", "aac", "-b:a", "192k"]
    args.append(str(out_path))
    _run(args)


def _filter_path(path: Path) -> str:
    """FFmpeg ใช้ ':' แยกพารามิเตอร์ใน filter — path แบบ D:\\... ต้อง escape ก่อน"""
    return path.as_posix().replace("\\", "/").replace(":", r"\:")


def finalize(video: Path, voice: Path, subs: Path, out_path: Path, cfg: dict) -> None:
    """รวมเสียงพากย์ + เพลงประกอบ + เบิร์นซับ"""
    fonts_dir = _filter_path(ASSETS / "fonts")
    subs_arg = _filter_path(subs)
    music = _pick_music()

    if music:
        filter_complex = (
            f"[1:a]volume=1.0[voice];"
            f"[2:a]aloop=loop=-1:size=2e9,volume=0.07[bed];"
            f"[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        inputs = ["-i", str(video), "-i", str(voice), "-i", str(music)]
        maps = ["-map", "0:v", "-map", "[aout]", "-filter_complex", filter_complex]
    else:
        inputs = ["-i", str(video), "-i", str(voice)]
        maps = ["-map", "0:v", "-map", "1:a"]

    _run([
        "ffmpeg", "-y", *inputs, *maps,
        "-vf", f"subtitles='{subs_arg}':fontsdir='{fonts_dir}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(out_path),
    ])


def _pick_music() -> Path | None:
    tracks = sorted((ASSETS / "music").glob("*.mp3"))
    return random.choice(tracks) if tracks else None
