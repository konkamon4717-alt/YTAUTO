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
from .steps import animate, images, render, script, subtitles, thumbnail, voice


def _slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _build_clips(scenes: list[dict], stills: list[Path], durations: list[float],
                 cfg: dict, work: Path) -> tuple[list[Path], dict]:
    """ทำคลิปของแต่ละฉาก พยายามให้ขยับทุกฉาก ฉากไหนไม่ได้ก็ใช้กล้องเคลื่อนบนภาพนิ่งแทน

    ไล่ทำจากฉากสำคัญที่สุดก่อน เพื่อว่าถ้าโควต้าหมดกลางทาง ฉากที่เสียไปจะเป็นฉากที่
    คนดูสังเกตน้อยที่สุด ไม่ใช่ฉากฮุกหรือฉากหักมุม
    """
    clips: list[Path | None] = [None] * len(scenes)

    if not cfg["animation"]["enabled"]:
        order: list[int] = []
    else:
        order = sorted(range(len(scenes)),
                       key=lambda i: -int(scenes[i].get("importance", 3)))[
                           : cfg["animation"]["max_shots_per_run"]]

    animator = animate.Animator({**cfg, "_work": str(work)})
    shots = [
        animate.Shot(
            image=stills[i],
            prompt=scenes[i].get("motion") or scenes[i]["image_prompt"],
            seconds=durations[i],
        )
        for i in order
    ]
    raws = [work / f"raw_{i:02d}.mp4" for i in order]

    if shots:
        winners = animator.animate_all(shots, raws)
        for index, raw, backend in zip(order, raws, winners):
            if not backend or not raw.exists():
                continue
            clip = work / f"clip_{index:02d}.mp4"
            render.conform(raw, durations[index], clip, cfg, work)
            clips[index] = clip
            print(f"      ฉาก {index + 1} ขยับแล้ว ({backend})")

    for index, clip in enumerate(clips):
        if clip is None:
            fallback = work / f"clip_{index:02d}.mp4"
            move = render.CAMERA_MOVES[index % len(render.CAMERA_MOVES)]
            render.ken_burns(stills[index], durations[index], fallback, cfg, move=move)
            clips[index] = fallback

    animated = sum(animator.used.values())
    print(f"      สรุป: ขยับ {animated}/{len(scenes)} ฉาก ({animator.summary()})")
    return [c for c in clips if c], {"animated": animated,
                                     "scenes": len(scenes),
                                     "backends": dict(animator.used)}


def make_video(cfg: dict, work: Path, story: dict | None = None) -> tuple[Path, dict, dict]:
    work.mkdir(parents=True, exist_ok=True)

    if story is None:
        print("[1/6] ให้ Gemini คิดเรื่อง...")
        story = script.generate(cfg, state.recent_premises())
    else:
        print("[1/6] ใช้เรื่องจากไฟล์ที่กำหนดมา (ข้าม Gemini)")
    print(f"      เรื่อง: {story['title']}")

    print("[2/6] พากย์เสียงทีละฉาก...")
    voice_parts: list[Path] = []
    scene_lines: list[dict] = []
    offset = 0.0
    scene_durations: list[float] = []

    # พากย์ทั้งคลิปรวดเดียวด้วยเสียงเดียวกัน ไม่ใช่เลือกตัวพากย์ทีละฉาก
    # ไม่งั้นฉากที่ตัวหลักล้มจะได้เสียงคนละคน แล้วคลิปจะสลับเสียงกลางเรื่อง
    narrations = [s["narration"] for s in story["scenes"]]

    # ประโยคปิดของช่อง พากย์รวมไปกับฉากอื่นเพื่อให้เป็นเสียงเดียวกัน
    closing = (cfg.get("brand") or {}).get("closing_line", "").strip()
    if closing:
        narrations.append(closing)

    parts = [work / f"voice_{i:02d}.mp3" for i in range(len(narrations))]
    spoken_all = voice.speak_all(narrations, parts, cfg)
    voice_backend = spoken_all[0]["backend"]

    for index, scene in enumerate(story["scenes"]):
        part = parts[index]
        spoken = spoken_all[index]
        seconds = render.duration_of(part)

        if spoken["granularity"] == "word":
            lines = subtitles.group_words(
                spoken["segments"], cfg["subtitles"]["max_chars_per_line"],
                source=scene["narration"],
            )
        else:
            # ตัวสำรองพากย์ทีละวรรคอยู่แล้ว แต่ละวรรคจึงเป็นบรรทัดซับได้เลย
            lines = spoken["segments"]

        for line in lines:
            scene_lines.append({**line,
                                "start": line["start"] + offset,
                                "end": line["end"] + offset})

        voice_parts.append(part)
        scene_durations.append(seconds)
        offset += seconds

    # ฉากปิดต้องนับรวมในเพดานความยาวด้วย ไม่งั้นเรื่องที่ยาวพอดีจะทะลุเพดาน
    # หลังต่อฉากปิดโดยไม่มีอะไรจับได้
    outro_seconds = render.duration_of(parts[-1]) if closing else 0.0
    total = sum(scene_durations) + outro_seconds
    print(f"      ความยาวรวม {total:.1f} วินาที"
          + (f" (เรื่อง {total - outro_seconds:.1f} + ปิดท้าย {outro_seconds:.1f})"
             if closing else ""))
    if total > cfg["video"]["hard_max_seconds"]:
        raise RuntimeError(
            f"ยาวเกิน ({total:.1f}s > {cfg['video']['hard_max_seconds']}s) — ทิ้งรอบนี้แล้วให้ไปคิดใหม่"
        )

    scenes = story["scenes"]

    print("[3/6] สร้างภาพประกอบ...")
    stills: list[Path] = []
    seed = int(time.time())
    for index, scene in enumerate(scenes):
        image_path = work / f"scene_{index:02d}.jpg"
        prompt = images.build_prompt(
            scene["image_prompt"], story["character_sheet"], cfg["images"]["style"],
            has_main_character=scene.get("has_main_character", True),
        )
        images.fetch(prompt, image_path, cfg, seed=seed + index)
        stills.append(image_path)
        print(f"      ภาพ {index + 1}/{len(scenes)}")

    print("[4/6] ทำให้ภาพขยับ...")
    clips, anim_stats = _build_clips(scenes, stills, scene_durations, cfg, work)

    if closing:
        outro_spoken = spoken_all[-1]
        outro_path = parts[-1]

        lines = (subtitles.group_words(
                     outro_spoken["segments"], cfg["subtitles"]["max_chars_per_line"],
                     source=closing)
                 if outro_spoken["granularity"] == "word"
                 else outro_spoken["segments"])
        for line in lines:
            scene_lines.append({**line,
                                "start": line["start"] + offset,
                                "end": line["end"] + offset})

        outro_clip = work / f"clip_{len(scenes):02d}.mp4"
        # ใช้ภาพฉากสุดท้ายซ้ำ ซูมออกช้า ๆ ให้รู้สึกว่าเรื่องจบลง
        render.ken_burns(stills[-1], outro_seconds, outro_clip, cfg, move="out")
        clips.append(outro_clip)
        voice_parts.append(outro_path)
        print(f"      ต่อฉากปิดของช่อง ({outro_seconds:.1f} วินาที)")

    print("[5/6] ตัดต่อ...")
    subs_path = work / "subs.ass"
    subtitles.write_ass(scene_lines, subs_path, cfg)

    silent = work / "silent.mp4"
    voice_track = work / "voice.m4a"
    render.concat(clips, silent, work)
    render.concat(voice_parts, voice_track, work, reencode=True)

    final = work / "final.mp4"
    render.finalize(silent, voice_track, subs_path, final, cfg)
    print(f"      ได้ไฟล์ {final.name} ({final.stat().st_size / 1_000_000:.1f} MB)")

    if cfg["upload"].get("thumbnail"):
        try:
            # ใช้ภาพฉากแรกเพราะเป็นฉากฮุก ซึ่งเป็นภาพที่ตั้งใจให้สะดุดตาที่สุดอยู่แล้ว
            cover = thumbnail.make(stills[0], story["thumbnail_text"],
                                   work / "cover.jpg", work)
            cfg["_thumbnail"] = str(cover)
            print(f"      ทำปกคลิปแล้ว: \"{story['thumbnail_text']}\"")
        except Exception as exc:  # noqa: BLE001 - ไม่มีปกก็ยังปล่อยคลิปได้
            print(f"      ทำปกไม่สำเร็จ: {str(exc)[:130]}")

    anim_stats["voice"] = voice_backend
    return final, story, anim_stats


def run_once(cfg: dict, upload_enabled: bool, story: dict | None = None) -> dict:
    work = config.OUT / _slug()
    started = time.time()

    try:
        final, story, anim_stats = make_video(cfg, work, story)

        video_id = None
        if upload_enabled:
            print("[6/6] อัปโหลดขึ้น YouTube...")
            from .steps import upload as uploader
            video_id = uploader.upload(final, story, cfg)
            print(f"      https://youtube.com/watch?v={video_id}")
        else:
            print("[6/6] ข้ามการอัปโหลด (โหมดทดลอง)")

        entry = {
            "ok": True,
            "title": story["title"],
            "premise": story["premise"],
            "video_id": video_id,
            "seconds": round(time.time() - started),
            "writer": story.get("_writer"),
            **anim_stats,
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
