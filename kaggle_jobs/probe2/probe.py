"""หาค่าตั้งที่ทำให้ LTX ไม่พังบน T4

รอบแรกเจอว่าคลิปคมแค่เฟรมแรกแล้วสลายเป็นสีเบลอ (LTX collapse) สาเหตุที่เป็นไปได้:
  - ไม่ได้ส่ง guidance_scale ทำให้ใช้ค่า default ที่ไม่เหมาะ
  - ไม่ได้ส่ง decode_timestep / decode_noise_scale ซึ่ง LTX ต้องการ
  - รุ่น base ต้องใช้ steps เยอะ ส่วนรุ่น distilled ออกแบบมาให้ใช้ 8 steps

รอบนี้ลองหลายค่าแล้ววัด "ความคมของแต่ละเฟรม" เป็นตัวเลข (ความแปรปรวนของ Laplacian)
ถ้าค่าร่วงลงเรื่อย ๆ แปลว่าภาพกำลังสลาย ไม่ต้องเปิดดูทีละคลิปเอง
"""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

OUT = Path("/kaggle/working")
REPORT = {"configs": []}

IMAGE_URL = (
    "https://image.pollinations.ai/prompt/"
    "a%20boy%20holding%20a%20basket%20of%20eggs%20storybook%20illustration"
    "?width=704&height=1216&nologo=true&seed=7"
)
PROMPT = "subtle natural motion, gentle breathing, slow cinematic camera push in"
NEGATIVE = ("worst quality, inconsistent motion, blurry, jittery, distorted, "
            "morphing face, melting, watermark, text")


def save() -> None:
    (OUT / "probe2_result.json").write_text(
        json.dumps(REPORT, indent=2, default=str), encoding="utf-8"
    )


def sharpness_curve(frames) -> list[float]:
    """ความคมของแต่ละเฟรม — ค่าร่วงต่อเนื่อง = ภาพกำลังสลาย"""
    import numpy as np
    curve = []
    for frame in frames:
        arr = np.asarray(frame.convert("L"), dtype=np.float32)
        # Laplacian แบบง่าย: ผลต่างกับเพื่อนบ้าน ยิ่งแปรปรวนมาก ยิ่งมีรายละเอียด
        lap = (arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:]
               - 4 * arr[1:-1, 1:-1])
        curve.append(round(float(lap.var()), 1))
    return curve


def verdict(curve: list[float]) -> str:
    if not curve:
        return "ไม่มีเฟรม"
    first, last = curve[0], curve[-1]
    keep = last / first if first else 0
    if keep < 0.35:
        return f"พัง (เหลือความคม {keep:.0%})"
    if keep < 0.65:
        return f"เสื่อม (เหลือ {keep:.0%})"
    return f"ดี (เหลือ {keep:.0%})"


def main() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "diffusers>=0.32.0", "transformers>=4.47.0",
                    "accelerate", "imageio[ffmpeg]", "numpy"], check=True)

    import torch
    from diffusers import LTXImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    props = torch.cuda.get_device_properties(0)
    REPORT["gpu"] = {"name": props.name, "vram_gb": round(props.total_memory / 1e9, 1)}
    save()

    image = load_image(IMAGE_URL)

    # (ชื่อรุ่น, steps, guidance, dtype)
    CONFIGS = [
        ("Lightricks/LTX-Video-0.9.7-distilled", 8, 1.0, torch.bfloat16),
        ("Lightricks/LTX-Video", 30, 3.0, torch.bfloat16),
        ("Lightricks/LTX-Video", 30, 3.0, torch.float16),
    ]

    loaded: dict = {}
    for repo, steps, guidance, dtype in CONFIGS:
        tag = f"{repo.split('/')[-1]}_s{steps}_g{guidance}_{str(dtype).split('.')[-1]}"
        entry = {"repo": repo, "steps": steps, "guidance": guidance,
                 "dtype": str(dtype), "tag": tag}
        try:
            key = (repo, dtype)
            if key not in loaded:
                t0 = time.time()
                pipe = LTXImageToVideoPipeline.from_pretrained(repo, torch_dtype=dtype)
                pipe.enable_model_cpu_offload()
                loaded.clear()          # T4 มี VRAM จำกัด ถือไว้ทีละรุ่นพอ
                loaded[key] = pipe
                entry["model_load_seconds"] = round(time.time() - t0)
            pipe = loaded[key]

            t0 = time.time()
            frames = pipe(
                image=image, prompt=PROMPT, negative_prompt=NEGATIVE,
                width=704, height=1216, num_frames=97,
                num_inference_steps=steps, guidance_scale=guidance,
                # สองค่านี้คือตัวที่รอบแรกไม่ได้ส่ง เป็นค่าที่ LTX แนะนำ
                decode_timestep=0.05, decode_noise_scale=0.025,
            ).frames[0]
            entry["seconds"] = round(time.time() - t0)

            curve = sharpness_curve(frames)
            entry["sharpness_first"] = curve[0]
            entry["sharpness_last"] = curve[-1]
            entry["sharpness_every_10th"] = curve[::10]
            entry["verdict"] = verdict(curve)

            export_to_video(frames, str(OUT / f"{tag}.mp4"), fps=24)
        except Exception as exc:  # noqa: BLE001 - config ไหนพังก็ข้ามไปตัวถัดไป
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc()[-900:]

        REPORT["configs"].append(entry)
        print(json.dumps(entry, ensure_ascii=False)[:400], flush=True)
        save()

    print("PROBE2 DONE", flush=True)


main()
