"""Wan 2.2 TI2V-5B ใส่ T4 ได้ไหม

ถ้าได้ = ได้ทั้งคุณภาพของ Wan และโควต้าเยอะของ Kaggle พร้อมกัน ซึ่งเป็นผลลัพธ์ที่ดีที่สุด
ถ้าไม่ได้ = ต้องใช้ Wan ผ่าน Hugging Face ซึ่งจำกัด ~7 ช็อต/วัน

จุดที่น่าจะติดคือ text encoder ของ Wan (UMT5-XXL) ตัวใหญ่มาก ไม่ใช่ตัวโมเดลวิดีโอเอง
จึงลองสามระดับของการประหยัดหน่วยความจำ จากเบาไปหนัก
  1. model cpu offload  — ย้ายทีละบล็อกใหญ่ เร็วสุด กินแรมมากสุด
  2. sequential offload — ย้ายทีละชั้น ช้ากว่ามาก แต่กินแรมน้อยสุด
  3. sequential + ความละเอียดต่ำลง — ทางสุดท้ายก่อนยอมแพ้
"""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

OUT = Path("/kaggle/working")
REPORT = {"attempts": []}

IMAGE_URL = ("https://image.pollinations.ai/prompt/"
             "a%20boy%20counting%20eggs%20into%20a%20basket%20at%20a%20market%20stall"
             "%20storybook%20illustration?width=704&height=1216&nologo=true&seed=11")
PROMPT = "the boy moves his hands slowly over the eggs, gentle breathing, slow camera push in"
NEGATIVE = ("worst quality, blurry, melting, dissolving, morphing face, distorted hands, "
            "flickering, smearing, watermark, text")
REPO = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"


def save() -> None:
    (OUT / "probe5_result.json").write_text(
        json.dumps(REPORT, indent=2, default=str), encoding="utf-8")


def decay_curve(frames) -> list[float]:
    import numpy as np
    base = np.asarray(frames[0].convert("L"), dtype=np.float32)
    return [round(float(np.abs(np.asarray(f.convert("L"), dtype=np.float32) - base).mean()), 2)
            for f in frames[::8]]


def attempt(tag: str, offload: str, W: int, H: int, NF: int) -> dict:
    import torch
    from diffusers import WanImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    entry = {"tag": tag, "offload": offload, "size": f"{W}x{H}", "frames": NF}
    pipe = None
    try:
        t0 = time.time()
        pipe = WanImageToVideoPipeline.from_pretrained(REPO, torch_dtype=torch.float16)
        pipe.vae.enable_tiling()
        if offload == "sequential":
            pipe.enable_sequential_cpu_offload()
        else:
            pipe.enable_model_cpu_offload()
        entry["load_seconds"] = round(time.time() - t0)

        t0 = time.time()
        frames = pipe(image=load_image(IMAGE_URL), prompt=PROMPT, negative_prompt=NEGATIVE,
                      width=W, height=H, num_frames=NF,
                      num_inference_steps=30, guidance_scale=5.0).frames[0]
        entry["seconds"] = round(time.time() - t0)
        entry["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 1)

        export_to_video(frames, str(OUT / f"{tag}.mp4"), fps=16)
        curve = decay_curve(frames)
        entry["decay_curve"] = curve
        # ภาพที่สลายจะต่างจากเฟรมแรกมากขึ้นเรื่อย ๆ ภาพที่ขยับปกติจะขึ้นแล้วทรงตัว
        mid, last = curve[len(curve) // 2] or 1, curve[-1]
        entry["verdict"] = ("สลายต่อเนื่อง" if last / mid > 1.6
                            else f"ทรงตัว (ครึ่งหลัง {last/mid:.2f} เท่า)")
        entry["ok"] = True
    except Exception as exc:  # noqa: BLE001 - แต่ละระดับพังได้ ต้องลองระดับถัดไป
        entry["ok"] = False
        entry["error"] = f"{type(exc).__name__}: {exc}"[:260]
    finally:
        if pipe is not None:
            del pipe
        try:
            import torch as t
            t.cuda.empty_cache()
            t.cuda.reset_peak_memory_stats()
        except Exception:
            pass
    return entry


PLAN = [
    ("wan_model_offload_704", "model",      704, 1216, 49),
    ("wan_seq_offload_704",   "sequential", 704, 1216, 49),
    ("wan_seq_offload_480",   "sequential", 480, 832,  49),
]


def main() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "diffusers>=0.35.0", "transformers>=4.51.0",
                    "accelerate", "imageio[ffmpeg]", "ftfy", "numpy"], check=True)
    import torch
    props = torch.cuda.get_device_properties(0)
    REPORT["gpu"] = {"name": props.name, "vram_gb": round(props.total_memory / 1e9, 1)}
    save()

    for tag, offload, W, H, NF in PLAN:
        entry = attempt(tag, offload, W, H, NF)
        REPORT["attempts"].append(entry)
        print(json.dumps(entry, ensure_ascii=False)[:320], flush=True)
        save()
        if entry.get("ok"):
            break   # ระดับที่เบาที่สุดที่ผ่านคือระดับที่เราต้องการ ไม่ต้องลองต่อ

    print("PROBE5 DONE", flush=True)


try:
    main()
except Exception as exc:  # noqa: BLE001
    REPORT["fatal"] = f"{type(exc).__name__}: {exc}"
    REPORT["traceback"] = traceback.format_exc()[-1200:]
    save()
    raise
