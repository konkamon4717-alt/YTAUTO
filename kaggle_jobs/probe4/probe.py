"""หาโมเดล/ค่าตั้งที่ไม่ละลาย

บทเรียนจากรอบก่อน: วัดความคมเป็นตัวเลขแล้วผ่าน แต่พอเปิดดูจริงภาพละลายเป็นก้อนสีน้ำตาล
ตัววัดแบบความแปรปรวนจับอาการ "เบลอเป็นเนื้อเดียว" ไม่ได้ รอบนี้จึงเพิ่มตัววัดที่ตรงกว่า
คือ "ความต่างจากเฟรมแรก" — ถ้าภาพสลายไปเรื่อย ๆ ค่านี้จะพุ่งขึ้นไม่หยุด
และเซฟคลิปทุกตัวกลับมาให้เปิดดูด้วยตาเสมอ

สมมติฐานที่จะทดสอบ:
  1. LTX ยาว 2 วินาทีแทน 4 — อาการสะสมตามจำนวนเฟรม ตัดสั้นลงน่าจะรอด
  2. LTX ความละเอียดสูงขึ้น — รอบก่อน 704x1216 คงสภาพดีกว่า 512x896
  3. Wan 2.2 TI2V-5B — คนละโมเดล ตัวที่รันบน HF ไม่ละลายเลย
"""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

OUT = Path("/kaggle/working")
REPORT = {"configs": []}

IMAGE_URL = ("https://image.pollinations.ai/prompt/"
             "a%20boy%20counting%20eggs%20into%20a%20basket%20at%20a%20market%20stall"
             "%20storybook%20illustration?width=704&height=1216&nologo=true&seed=11")
PROMPT = "the boy moves his hands slowly over the eggs, gentle breathing, slow camera push in"
NEGATIVE = ("worst quality, blurry, melting, dissolving, morphing face, distorted hands, "
            "flickering, smearing, watermark, text")


def save() -> None:
    (OUT / "probe4_result.json").write_text(
        json.dumps(REPORT, indent=2, default=str), encoding="utf-8")


def decay_curve(frames) -> list[float]:
    """ความต่างของแต่ละเฟรมเทียบกับเฟรมแรก

    ภาพที่ขยับปกติจะต่างขึ้นแล้วทรงตัว ภาพที่สลายจะต่างขึ้นเรื่อย ๆ ไม่หยุด
    """
    import numpy as np
    base = np.asarray(frames[0].convert("L"), dtype=np.float32)
    out = []
    for f in frames[::10]:
        arr = np.asarray(f.convert("L"), dtype=np.float32)
        out.append(round(float(np.abs(arr - base).mean()), 2))
    return out


def verdict(curve: list[float]) -> str:
    if len(curve) < 3:
        return "สั้นเกินกว่าจะตัดสิน"
    head, tail = curve[len(curve) // 2], curve[-1]
    if head and tail / head > 1.6:
        return f"สลายต่อเนื่อง (ครึ่งหลังพุ่ง {tail/head:.1f} เท่า)"
    return f"ทรงตัว (ครึ่งหลังเปลี่ยน {tail/head if head else 0:.2f} เท่า)"


def run_ltx(repo, steps, guidance, W, H, NF, tag, entry):
    import torch
    from diffusers import LTXImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image
    t0 = time.time()
    pipe = LTXImageToVideoPipeline.from_pretrained(repo, torch_dtype=torch.float16)
    pipe.vae.enable_tiling()
    pipe.enable_model_cpu_offload()
    entry["load_seconds"] = round(time.time() - t0)

    t0 = time.time()
    frames = pipe(image=load_image(IMAGE_URL), prompt=PROMPT, negative_prompt=NEGATIVE,
                  width=W, height=H, num_frames=NF, num_inference_steps=steps,
                  guidance_scale=guidance,
                  decode_timestep=0.05, decode_noise_scale=0.025).frames[0]
    entry["seconds"] = round(time.time() - t0)
    export_to_video(frames, str(OUT / f"{tag}.mp4"), fps=24)
    del pipe
    torch.cuda.empty_cache()
    return frames


def run_wan(W, H, NF, tag, entry):
    import torch
    from diffusers import WanImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image
    t0 = time.time()
    pipe = WanImageToVideoPipeline.from_pretrained(
        "Wan-AI/Wan2.2-TI2V-5B-Diffusers", torch_dtype=torch.float16)
    pipe.vae.enable_tiling()
    pipe.enable_model_cpu_offload()
    entry["load_seconds"] = round(time.time() - t0)

    t0 = time.time()
    frames = pipe(image=load_image(IMAGE_URL), prompt=PROMPT, negative_prompt=NEGATIVE,
                  width=W, height=H, num_frames=NF, num_inference_steps=30,
                  guidance_scale=5.0).frames[0]
    entry["seconds"] = round(time.time() - t0)
    export_to_video(frames, str(OUT / f"{tag}.mp4"), fps=16)
    del pipe
    torch.cuda.empty_cache()
    return frames


CONFIGS = [
    ("ltx_2s_512",  lambda e: run_ltx("Lightricks/LTX-Video", 30, 3.0, 512, 896, 49, "ltx_2s_512", e)),
    ("ltx_4s_704",  lambda e: run_ltx("Lightricks/LTX-Video", 30, 3.0, 704, 1216, 97, "ltx_4s_704", e)),
    ("wan22_5b",    lambda e: run_wan(704, 1216, 49, "wan22_5b", e)),
]


def main() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "diffusers>=0.33.0", "transformers>=4.49.0",
                    "accelerate", "imageio[ffmpeg]", "ftfy", "numpy"], check=True)
    import torch
    REPORT["gpu"] = torch.cuda.get_device_name(0)
    save()

    for tag, fn in CONFIGS:
        entry = {"tag": tag}
        try:
            frames = fn(entry)
            curve = decay_curve(frames)
            entry["decay_curve"] = curve
            entry["verdict"] = verdict(curve)
            entry["ok"] = True
        except Exception as exc:  # noqa: BLE001 - config ไหนพังก็ข้ามไปตัวถัดไป
            entry["ok"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            entry["traceback"] = traceback.format_exc()[-700:]
        REPORT["configs"].append(entry)
        print(json.dumps(entry, ensure_ascii=False)[:350], flush=True)
        save()

    print("PROBE4 DONE", flush=True)


try:
    main()
except Exception as exc:  # noqa: BLE001 - ต้องเขียนรายงานเสมอ
    REPORT["fatal"] = f"{type(exc).__name__}: {exc}"
    REPORT["traceback"] = traceback.format_exc()[-1200:]
    save()
    raise
