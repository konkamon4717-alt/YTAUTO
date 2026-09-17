"""วัดว่า Kaggle ให้ GPU อะไรมา และรันโมเดลวิดีโอได้เร็วแค่ไหน

รันบน Kaggle เท่านั้น ไม่ใช่โค้ดของระบบหลัก
เป้าหมายคือเก็บตัวเลขจริงก่อนออกแบบ backend จะได้ไม่เดา:
  - GPU รุ่นไหน VRAM เท่าไหร่ compute capability เท่าไหร่ (มีผลว่าใช้ fp16/bf16/fp8 ได้ไหม)
  - โหลดโมเดลนานแค่ไหน (ต้นทุนคงที่ต่อรอบ)
  - สร้างวิดีโอ 1 ช็อตนานแค่ไหน (ต้นทุนผันแปรต่อช็อต)

ผลลัพธ์ออกเป็น /kaggle/working/probe_result.json
"""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

OUT = Path("/kaggle/working")
REPORT = {"stages": {}}


def record(stage: str, **data) -> None:
    REPORT["stages"][stage] = data
    print(f"[{stage}] {data}", flush=True)
    (OUT / "probe_result.json").write_text(
        json.dumps(REPORT, indent=2, default=str), encoding="utf-8"
    )


def stage_hardware() -> None:
    import torch
    props = torch.cuda.get_device_properties(0) if torch.cuda.is_available() else None
    record(
        "hardware",
        cuda=torch.cuda.is_available(),
        gpu=props.name if props else None,
        vram_gb=round(props.total_memory / 1e9, 1) if props else 0,
        capability=f"{props.major}.{props.minor}" if props else None,
        torch=torch.__version__,
        # fp8 ต้อง compute capability >= 8.9 (Ada/Hopper) ไม่งั้นต้องถอยไป fp16
        supports_bf16=torch.cuda.is_bf16_supported() if props else False,
    )


def stage_install() -> None:
    t0 = time.time()
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q",
         "diffusers>=0.32.0", "transformers>=4.47.0", "accelerate", "imageio[ffmpeg]"],
        check=True,
    )
    record("install", seconds=round(time.time() - t0))


def stage_generate() -> None:
    import torch
    from diffusers import LTXImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    t0 = time.time()
    pipe = LTXImageToVideoPipeline.from_pretrained(
        "Lightricks/LTX-Video", torch_dtype=torch.float16
    )
    pipe.enable_model_cpu_offload()
    record("model_load", seconds=round(time.time() - t0))

    image = load_image(
        "https://image.pollinations.ai/prompt/"
        "a%20boy%20holding%20a%20basket%20of%20eggs%20storybook%20illustration"
        "?width=704&height=1216&nologo=true&seed=7"
    )

    for label, steps in (("warm", 20), ("measured", 20)):
        t0 = time.time()
        frames = pipe(
            image=image,
            prompt="subtle natural motion, gentle breathing, slow cinematic camera push in",
            negative_prompt="morphing face, distorted hands, flickering, watermark, text",
            width=704, height=1216,
            num_frames=97,          # ~4 วินาทีที่ 24fps
            num_inference_steps=steps,
        ).frames[0]
        seconds = round(time.time() - t0)
        record(f"generate_{label}", seconds=seconds, frames=len(frames), steps=steps)

    export_to_video(frames, str(OUT / "probe_clip.mp4"), fps=24)
    record("saved", file="probe_clip.mp4",
           size_mb=round((OUT / "probe_clip.mp4").stat().st_size / 1e6, 2))


def main() -> None:
    for name, fn in (("hardware", stage_hardware),
                     ("install", stage_install),
                     ("generate", stage_generate)):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - probe ต้องรายงานผลเสมอแม้จะพัง
            record(f"{name}_FAILED", error=f"{type(exc).__name__}: {exc}",
                   traceback=traceback.format_exc()[-1500:])
            break
    print("PROBE DONE", flush=True)


main()
