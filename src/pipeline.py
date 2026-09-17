"""ตัวคุมงานหลัก: คิดเรื่อง -> พากย์ -> วาดภาพ -> ตัดต่อ -> อัปโหลด"""
import argparse
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import config, state, status
from .steps import images, render, script, subtitles, voice


def _slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def make_video(cfg: dict, work: Path, story: dict | None = None) -> tuple[Path, dict]:
    work.mkdir(parents=True, exist_ok=True)

    if story is None:
        print("[1/5] ให้ Gemini คิดเรื่อง...")
        story = script.generate(cfg, state.recent_premises())
    else:
        print("[1/5] ใช้เรื่องจากไฟล์ที่กำหนดมา (ข้าม Gemini)")
    print(f"      เรื่อง: {story['title']}")

    print("[2/5] พากย์เสียงทีละฉาก...")
    voice_parts: list[Path] = []
    scene_lines: list[dict] = []
    offset = 0.0
    scene_durations: list[float] = []

    for index, scene in enumerate(story["scenes"]):
        part = work / f"voice_{index:02d}.mp3"
        words = voice.speak(scene["narration"], part, cfg)
        seconds = render.duration_of(part)

        lines = subtitles.group_words(
            words, cfg["subtitles"]["max_chars_per_line"], source=scene["narration"]
        )
        for line in lines:
            scene_lines.append({**line,
                                "start": line["start"] + offset,
                                "end": line["end"] + offset})

        voice_parts.append(part)
        scene_durations.append(seconds)
        offset += seconds

    total = sum(scene_durations)
    print(f"      ความยาวรวม {total:.1f} วินาที")
    if total > cfg["video"]["hard_max_seconds"]:
        raise RuntimeError(
            f"เรื่องยาวเกิน ({total:.1f}s > {cfg['video']['hard_max_seconds']}s) — ทิ้งรอบนี้แล้วให้ไปคิดใหม่"
        )

    print("[3/5] สร้างภาพประกอบ...")
    clips: list[Path] = []
    seed = int(time.time())
    for index, scene in enumerate(story["scenes"]):
        image_path = work / f"scene_{index:02d}.jpg"
        prompt = images.build_prompt(
            scene["image_prompt"], story["character_sheet"], cfg["images"]["style"],
            has_main_character=scene.get("has_main_character", True),
        )
        images.fetch(prompt, image_path, cfg, seed=seed + index)

        clip = work / f"clip_{index:02d}.mp4"
        render.ken_burns(image_path, scene_durations[index], clip, cfg,
                         zoom_in=index % 2 == 0)
        clips.append(clip)
        print(f"      ฉาก {index + 1}/{len(story['scenes'])} เสร็จ")

    print("[4/5] ตัดต่อ...")
    subs_path = work / "subs.ass"
    subtitles.write_ass(scene_lines, subs_path, cfg)

    silent = work / "silent.mp4"
    voice_track = work / "voice.m4a"
    render.concat(clips, silent, work)
    render.concat(voice_parts, voice_track, work, reencode=True)

    final = work / "final.mp4"
    render.finalize(silent, voice_track, subs_path, final, cfg)
    print(f"      ได้ไฟล์ {final.name} ({final.stat().st_size / 1_000_000:.1f} MB)")

    return final, story


def run_once(cfg: dict, upload_enabled: bool, story: dict | None = None) -> dict:
    work = config.OUT / _slug()
    started = time.time()

    try:
        final, story = make_video(cfg, work, story)

        video_id = None
        if upload_enabled:
            print("[5/5] อัปโหลดขึ้น YouTube...")
            from .steps import upload as uploader
            video_id = uploader.upload(final, story, cfg)
            print(f"      https://youtube.com/watch?v={video_id}")
        else:
            print("[5/5] ข้ามการอัปโหลด (โหมดทดลอง)")

        entry = {
            "ok": True,
            "title": story["title"],
            "premise": story["premise"],
            "video_id": video_id,
            "seconds": round(time.time() - started),
        }
        state.record(story["premise"], entry)
        return entry

    except Exception as exc:  # noqa: BLE001 - ต้องจับทุกอย่างเพื่อบันทึกสถานะ
        traceback.print_exc()
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "seconds": round(time.time() - started),
        }
    finally:
        if work.exists() and not _keep_work():
            shutil.rmtree(work, ignore_errors=True)


def _keep_work() -> bool:
    import os
    return os.environ.get("KEEP_WORK") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="สร้างและอัปโหลดนิทานสั้นอัตโนมัติ")
    parser.add_argument("--count", type=int, default=1, help="จำนวนคลิปในรอบนี้")
    parser.add_argument("--no-upload", action="store_true", help="สร้างอย่างเดียว ไม่อัปโหลด")
    parser.add_argument("--keep", action="store_true", help="ไม่ลบไฟล์ระหว่างทาง")
    parser.add_argument("--story", type=Path,
                        help="ใช้ไฟล์ JSON ที่มีอยู่แทนการเรียก Gemini (ไว้เทสต์หรือเรนเดอร์ซ้ำ)")
    args = parser.parse_args()

    if args.keep:
        import os
        os.environ["KEEP_WORK"] = "1"

    cfg = config.load()
    canned = None
    if args.story:
        canned = json.loads(args.story.read_text(encoding="utf-8"))

    results = []

    for n in range(args.count):
        print(f"\n===== คลิปที่ {n + 1}/{args.count} =====")
        result = run_once(cfg, upload_enabled=not args.no_upload, story=canned)
        results.append(result)
        status.record_run(result)

    failed = [r for r in results if not r["ok"]]
    print(f"\nสรุป: สำเร็จ {len(results) - len(failed)}/{len(results)}")
    for result in failed:
        print(f"  ล้มเหลว: {result['error']}")

    # ล้มบางคลิปไม่ถือว่ารอบพัง แต่ล้มหมดถือว่าพัง จะได้เด้งเตือน
    return 1 if failed and len(failed) == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
