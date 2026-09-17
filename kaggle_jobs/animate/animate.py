"""ทำภาพนิ่งให้ขยับด้วย LTX-Video บน GPU ฟรีของ Kaggle

รันบน Kaggle เท่านั้น ไม่ใช่โค้ดฝั่งเครื่องเรา

ทำทุกช็อตของรอบนั้นในการรันครั้งเดียว เพราะต้นทุนคงที่ต่อรอบสูงมาก
(ติดตั้งของ + โหลดโมเดล ~4 นาที) ถ้ายิงทีละช็อตจะเสียเวลาโหลดโมเดลซ้ำทุกครั้ง

ค่าที่ใช้มาจากการวัดจริงบน T4:
  - fp16 เท่านั้น — T4 ไม่มี bf16 แบบเนทีฟ PyTorch ขยายเป็น fp32 แล้ว OOM
  - vae.enable_tiling() — VAE ตอน decode 97 เฟรมคือตัวกินแรมหลัก
  - 512x896 / 30 steps = 150 วินาทีต่อช็อต ความคมคงเหลือ 96% (ไม่สลาย)
  - ถ้าไม่ส่ง decode_timestep/decode_noise_scale ภาพจะสลายเป็นสีเบลอตั้งแต่กลางคลิป
"""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

OUT = Path("/kaggle/working")
INPUT_ROOT = Path("/kaggle/input")

WIDTH, HEIGHT = 512, 896
STEPS, GUIDANCE = 30, 3.0
FPS = 24

NEGATIVE = ("worst quality, inconsistent motion, blurry, jittery, distorted, "
            "morphing face, melting, extra fingers, watermark, text, subtitles")
MOTION_SUFFIX = ("subtle natural motion, gentle movement, slow cinematic camera, "
                 "consistent character, stable composition")

report = {"shots": []}


def save_report() -> None:
    (OUT / "animate_result.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")


def find_jobs() -> tuple[Path, list[dict]]:
    """หาไฟล์ jobs.json ที่แนบมากับ dataset"""
    for candidate in INPUT_ROOT.rglob("jobs.json"):
        return candidate.parent, json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError("ไม่พบ jobs.json ใน /kaggle/input")


def frames_for(seconds: float) -> int:
    """LTX ต้องการจำนวนเฟรมแบบ 8k+1 และอย่างน้อย 1 วินาที"""
    wanted = max(int(round(seconds * FPS)), FPS)
    return ((wanted - 1) // 8) * 8 + 1


def main() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "diffusers>=0.32.0", "transformers>=4.47.0",
                    "accelerate", "imageio[ffmpeg]"], check=True)

    import torch
    from diffusers import LTXImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    folder, jobs = find_jobs()
    report["gpu"] = torch.cuda.get_device_name(0)
    report["job_count"] = len(jobs)
    save_report()

    t0 = time.time()
    pipe = LTXImageToVideoPipeline.from_pretrained(
        "Lightricks/LTX-Video", torch_dtype=torch.float16)
    pipe.vae.enable_tiling()
    pipe.enable_model_cpu_offload()
    report["model_load_seconds"] = round(time.time() - t0)
    save_report()

    for job in jobs:
        entry = {"id": job["id"]}
        started = time.time()
        try:
            image = load_image(str(folder / job["file"]))
            num_frames = frames_for(job.get("seconds", 4))
            frames = pipe(
                image=image,
                prompt=f"{job['prompt']}. {MOTION_SUFFIX}",
                negative_prompt=NEGATIVE,
                width=WIDTH, height=HEIGHT, num_frames=num_frames,
                num_inference_steps=STEPS, guidance_scale=GUIDANCE,
                decode_timestep=0.05, decode_noise_scale=0.025,
            ).frames[0]
            export_to_video(frames, str(OUT / f"{job['id']}.mp4"), fps=FPS)
            entry["seconds"] = round(time.time() - started)
            entry["frames"] = len(frames)
            entry["ok"] = True
        except Exception as exc:  # noqa: BLE001 - ช็อตเดียวพังต้องไม่ล้มทั้งรอบ
            entry["ok"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            entry["traceback"] = traceback.format_exc()[-600:]

        report["shots"].append(entry)
        print(json.dumps(entry, ensure_ascii=False)[:250], flush=True)
        save_report()

    done = sum(1 for s in report["shots"] if s.get("ok"))
    print(f"ANIMATE DONE {done}/{len(jobs)}", flush=True)


try:
    main()
except Exception as exc:  # noqa: BLE001 - ต้องเขียนรายงานเสมอแม้พังตั้งแต่ต้น
    report["fatal"] = f"{type(exc).__name__}: {exc}"
    report["traceback"] = traceback.format_exc()[-1200:]
    save_report()
    raise
