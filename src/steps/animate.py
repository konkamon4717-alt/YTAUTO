"""ทำให้ภาพนิ่งขยับ

ออกแบบเป็นหลายชั้น เรียงจากดีสุดไปถูกสุด ชั้นไหนใช้ไม่ได้ก็ตกไปชั้นถัดไปเอง
ชั้นล่างสุด (parallax) ไม่มีวันล้ม ระบบจึงไม่มีทางไม่ได้คลิป ต่อให้ GPU ฟรีตันหมดทุกเจ้า

    modal        เร็วสุด คุมความละเอียดเองได้     เครดิตฟรี $30/เดือน
    kaggle       โควต้าเยอะสุด แต่ต้องรอคิว        30 ชม./สัปดาห์
    huggingface  ต่อง่ายสุด ไม่ต้องตั้งอะไร        ~7 ช็อต/วัน
    parallax     ไม่ใช่ AI แต่ไม่มีวันตัน           ฟรีไม่จำกัด
"""
import os
from dataclasses import dataclass
from pathlib import Path

HF_SPACE = "zerogpu-aoti/wan2-2-fp8da-aoti-faster"

MOTION_SUFFIX = (
    "subtle natural motion, gentle breathing, slow cinematic camera movement, "
    "consistent character, stable composition"
)
NEGATIVE = (
    "morphing face, distorted hands, extra fingers, flickering, warping, "
    "text, watermark, subtitles, jitter, fast motion"
)


class QuotaExhausted(RuntimeError):
    """โควต้าของชั้นนี้หมดแล้ว — ให้ตกไปชั้นถัดไป และอย่าลองชั้นนี้ซ้ำในรอบเดียวกัน"""


@dataclass
class Shot:
    """คำสั่งทำให้ภาพหนึ่งใบขยับ"""
    image: Path
    prompt: str
    seconds: float


def _hf_animate(shot: Shot, out_path: Path, cfg: dict) -> None:
    from gradio_client import Client, handle_file

    token = os.environ.get("HF_TOKEN") or None
    client = Client(HF_SPACE, token=token, verbose=False)

    try:
        result = client.predict(
            input_image=handle_file(str(shot.image)),
            prompt=f"{shot.prompt}. {MOTION_SUFFIX}",
            duration_seconds=_clamp(shot.seconds, 2.0, 5.0),
            api_name="/generate_video",
        )
    except Exception as exc:  # noqa: BLE001 - gradio ห่อ error ของ Space มาอีกชั้น
        if _is_quota_error(exc):
            raise QuotaExhausted(str(exc)[:200]) from exc
        raise

    video = result[0] if isinstance(result, (list, tuple)) else result
    if isinstance(video, dict):
        video = video.get("video")
    if not video:
        raise RuntimeError("Space ไม่ได้ส่งไฟล์วิดีโอกลับมา")

    out_path.write_bytes(Path(video).read_bytes())


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "quota" in text or "exceeded" in text or "zerogpu" in text


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


# ทะเบียนชั้น — modal กับ kaggle จะเสียบเพิ่มเมื่อสมัครบริการเสร็จ
BACKENDS = {
    "huggingface": _hf_animate,
}


class Animator:
    """เรียกชั้นต่าง ๆ ตามลำดับ และจำไว้ว่าชั้นไหนตันไปแล้วในรอบนี้"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.order = [n for n in cfg["animation"]["backends"] if n in BACKENDS]
        self.exhausted: set[str] = set()
        self.used: dict[str, int] = {}

    def animate(self, shot: Shot, out_path: Path) -> str | None:
        """คืนชื่อชั้นที่ทำสำเร็จ หรือ None ถ้าทุกชั้นใช้ไม่ได้ (ให้ผู้เรียกไปทำ parallax)"""
        for name in self.order:
            if name in self.exhausted:
                continue
            try:
                BACKENDS[name](shot, out_path, self.cfg)
                self.used[name] = self.used.get(name, 0) + 1
                return name
            except QuotaExhausted as exc:
                print(f"      [{name}] โควต้าหมด ({exc}) — ข้ามไปชั้นถัดไป")
                self.exhausted.add(name)
            except Exception as exc:  # noqa: BLE001 - บริการฟรีล้มได้สารพัดแบบ
                print(f"      [{name}] ล้มเหลว: {type(exc).__name__}: {str(exc)[:150]}")
        return None

    def summary(self) -> str:
        if not self.used:
            return "parallax ล้วน"
        return ", ".join(f"{k}={v}" for k, v in self.used.items())
