"""ทำให้ภาพนิ่งขยับ

ออกแบบเป็นหลายชั้น เรียงจากดีสุดไปถูกสุด ชั้นไหนใช้ไม่ได้ก็ตกไปชั้นถัดไปเอง
ชั้นล่างสุด (parallax ในฝั่ง pipeline) ไม่มีวันล้ม ระบบจึงไม่มีทางไม่ได้คลิป
ต่อให้ GPU ฟรีตันหมดทุกเจ้า

    kaggle       โควต้าเยอะสุด 30 ชม./สัปดาห์   ส่งทีเดียวทั้งรอบ รอ ~30-60 นาที
    huggingface  ต่อง่าย ไม่ต้องตั้งอะไร        ~7 ช็อต/วัน ได้ผลทันที
    (parallax)   ฝั่ง pipeline จัดการ           ฟรีไม่จำกัด

ทุก backend รับงานเป็น "ชุด" เพราะ Kaggle มีต้นทุนคงที่ต่อรอบสูงมาก
(ติดตั้งของ + โหลดโมเดล ~4 นาที) ยิงทีละช็อตคือเสียเวลาโหลดโมเดลซ้ำทุกครั้ง
"""
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

HF_SPACE = "zerogpu-aoti/wan2-2-fp8da-aoti-faster"

MOTION_SUFFIX = (
    "subtle natural motion, gentle breathing, slow cinematic camera movement, "
    "consistent character, stable composition"
)


class QuotaExhausted(RuntimeError):
    """โควต้าของชั้นนี้หมดแล้ว — ให้ตกไปชั้นถัดไป และอย่าลองชั้นนี้ซ้ำในรอบเดียวกัน"""


@dataclass
class Shot:
    """คำสั่งทำให้ภาพหนึ่งใบขยับ"""
    image: Path
    prompt: str
    seconds: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "quota" in text or "exceeded" in text or "zerogpu" in text


# ---------- ชั้น Hugging Face ----------

def _hf_batch(shots: list[Shot], outs: list[Path], cfg: dict) -> list[bool]:
    """ยิงทีละช็อต หยุดทันทีที่โควต้าหมด ช็อตที่เหลือปล่อยให้ชั้นถัดไปรับ"""
    from gradio_client import Client, handle_file

    client = Client(HF_SPACE, token=os.environ.get("HF_TOKEN") or None, verbose=False)
    done = [False] * len(shots)

    for index, (shot, out) in enumerate(zip(shots, outs)):
        try:
            result = client.predict(
                input_image=handle_file(str(shot.image)),
                prompt=f"{shot.prompt}. {MOTION_SUFFIX}",
                duration_seconds=_clamp(shot.seconds, 2.0, 5.0),
                api_name="/generate_video",
            )
        except Exception as exc:  # noqa: BLE001 - gradio ห่อ error ของ Space มาอีกชั้น
            if _is_quota_error(exc):
                print(f"      [huggingface] โควต้าหมดที่ช็อตที่ {index + 1}")
                break
            print(f"      [huggingface] ช็อต {index + 1} ล้มเหลว: {str(exc)[:110]}")
            continue

        video = result[0] if isinstance(result, (list, tuple)) else result
        if isinstance(video, dict):
            video = video.get("video")
        if video:
            out.write_bytes(Path(video).read_bytes())
            done[index] = True

    return done


# ---------- ชั้น Kaggle ----------

def _kaggle_batch(shots: list[Shot], outs: list[Path], cfg: dict) -> list[bool]:
    """ส่งทุกช็อตไปรันรวดเดียวบน GPU ฟรีของ Kaggle แล้วรอผลกลับ"""
    from . import kaggle_gpu

    root = Path(cfg["_work"]) if cfg.get("_work") else outs[0].parent
    stage = root / "_kaggle_shots"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)

    jobs = []
    for index, shot in enumerate(shots):
        name = f"shot_{index:02d}.jpg"
        shutil.copy(shot.image, stage / name)
        jobs.append({"id": f"shot_{index:02d}", "file": name,
                     "prompt": shot.prompt, "seconds": shot.seconds})
    (stage / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False, indent=2),
                                     encoding="utf-8")

    slug = cfg["animation"]["kaggle_dataset"]
    full_slug = kaggle_gpu.ensure_dataset(stage, slug, title="yt-auto shots")
    kaggle_gpu.wait_for_dataset(full_slug)

    job_dir = Path(__file__).resolve().parents[2] / "kaggle_jobs" / "animate"
    kaggle_gpu.write_metadata(job_dir, slug=cfg["animation"]["kaggle_kernel"],
                              code_file="animate.py", dataset_sources=[full_slug])

    results = root / "_kaggle_out"
    shutil.rmtree(results, ignore_errors=True)
    files = kaggle_gpu.run_job(job_dir, results,
                              timeout_minutes=cfg["animation"]["kaggle_timeout_minutes"])

    by_name = {f.name: f for f in files}
    done = []
    for index, out in enumerate(outs):
        produced = by_name.get(f"shot_{index:02d}.mp4")
        if produced:
            out.write_bytes(produced.read_bytes())
            done.append(True)
        else:
            done.append(False)
    return done


BACKENDS = {
    "kaggle": _kaggle_batch,
    "huggingface": _hf_batch,
}


class Animator:
    """เรียกชั้นต่าง ๆ ตามลำดับ ช็อตที่ชั้นก่อนทำไม่ได้จะถูกส่งต่อให้ชั้นถัดไป"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.order = [n for n in cfg["animation"]["backends"] if n in BACKENDS]
        self.used: dict[str, int] = {}

    def animate_all(self, shots: list[Shot], outs: list[Path]) -> list[str | None]:
        """คืนชื่อชั้นที่ทำสำเร็จของแต่ละช็อต ช็อตที่ไม่สำเร็จเป็น None"""
        winners: list[str | None] = [None] * len(shots)
        pending = list(range(len(shots)))

        for name in self.order:
            if not pending:
                break
            subset = [shots[i] for i in pending]
            subset_outs = [outs[i] for i in pending]
            try:
                done = BACKENDS[name](subset, subset_outs, self.cfg)
            except Exception as exc:  # noqa: BLE001 - ชั้นนี้ใช้ไม่ได้ ไปชั้นถัดไป
                print(f"      [{name}] ใช้ไม่ได้: {type(exc).__name__}: {str(exc)[:160]}")
                continue

            still = []
            for position, index in enumerate(pending):
                if position < len(done) and done[position]:
                    winners[index] = name
                    self.used[name] = self.used.get(name, 0) + 1
                else:
                    still.append(index)
            pending = still

        return winners

    def summary(self) -> str:
        if not self.used:
            return "parallax ล้วน"
        return ", ".join(f"{k}={v}" for k, v in self.used.items())
