"""ส่ง probe ขึ้น Kaggle เพื่อวัดว่า GPU ฟรีที่ได้มาแรงแค่ไหน

  python tools/kaggle_probe.py

ใช้เวลาราว 15-30 นาที (เข้าคิว + ติดตั้งของ + โหลดโมเดล + สร้างวิดีโอ 2 รอบ)
ผลที่ได้จะบอกว่าทำได้กี่ช็อตต่อวันจริง ๆ ก่อนจะไปเขียน backend เต็ม
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.steps import kaggle_gpu  # noqa: E402

JOB = ROOT / "kaggle_jobs" / "probe"
DEST = ROOT / "out" / "_kaggle_probe"


def main() -> int:
    config._load_dotenv()

    kaggle_gpu.write_metadata(JOB, slug="yt-auto-probe", code_file="probe.py")
    print("ส่ง probe ขึ้น Kaggle — ใช้เวลาราว 15-30 นาที อย่าเพิ่งปิด")

    try:
        files = kaggle_gpu.run_job(JOB, DEST, timeout_minutes=50)
    except kaggle_gpu.KaggleError as exc:
        print("ล้มเหลว:", exc)
        return 1

    print(f"\nได้ไฟล์กลับมา {len(files)} ไฟล์:")
    for path in files:
        print(f"  {path.relative_to(DEST)}  ({path.stat().st_size / 1e6:.2f} MB)")

    report = next((p for p in files if p.name == "probe_result.json"), None)
    if not report:
        print("\nไม่พบ probe_result.json — ดู log ใน output ข้างบน")
        return 1

    data = json.loads(report.read_text(encoding="utf-8"))
    print("\n===== ผลการวัด =====")
    for stage, values in data.get("stages", {}).items():
        print(f"  {stage}: {values}")

    gen = data["stages"].get("generate_measured")
    if gen:
        per_shot = gen["seconds"]
        print(f"\nต่อ 1 ช็อต: {per_shot} วินาที")
        print(f"30 ชม./สัปดาห์ = {30 * 3600 // per_shot:,} ช็อต/สัปดาห์ "
              f"({30 * 3600 // per_shot // 7:,} ช็อต/วัน)")
        print("เราต้องใช้ 30 ช็อต/วัน (3 คลิป x 10 ฉาก)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
