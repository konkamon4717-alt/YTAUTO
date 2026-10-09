"""ขอ refresh token ของ YouTube ครั้งเดียว แล้วเขียนลง .env ให้เลย

วิธีใช้:
  1. ดาวน์โหลดไฟล์ client_secret_*.json จาก Google Cloud Console มาไว้โฟลเดอร์โปรเจกต์
  2. python tools/get_refresh_token.py --channel <ชื่อช่อง>
  3. เบราว์เซอร์จะเปิดให้ล็อกอิน **เลือกช่องให้ถูกตัว** ไม่ใช่แค่บัญชีให้ถูก
  4. สคริปต์เขียนค่าลง .env ให้เอง แล้วบอกว่าโทเค็นที่ได้เป็นของช่องไหนจริง ๆ

ชื่อช่องที่ใส่จะไปต่อท้ายชื่อตัวแปร เช่น --channel world ได้ YT_REFRESH_TOKEN_WORLD
ถ้าไม่ใส่จะเขียนทับตัวกลางซึ่งเป็นของช่องแรก — ตั้งใจให้ต้องพิมพ์เอง
เพราะเขียนทับโทเค็นของช่องที่ทำงานอยู่แปลว่าช่องนั้นหยุดลงคลิปทันที

สคริปต์นี้ "ไม่พิมพ์ค่า token ออกหน้าจอ" โดยตั้งใจ เพราะอะไรที่ถูกพิมพ์ออกมา
จะไปติดอยู่ใน log ของเทอร์มินัล ประวัติการรัน และหน้าต่างแชทที่เปิดดูอยู่

ก่อนรัน ให้แน่ใจว่า OAuth consent screen อยู่สถานะ "In production" แล้ว
ถ้ายังเป็น Testing อยู่ token ที่ได้จะหมดอายุใน 7 วัน
"""
import argparse
import glob
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    # สองอันนี้ไว้ดูยอดวิวรายวัน เวลาที่ดู และรายได้ในห้องควบคุม
    # ไม่มีก็อัปโหลดได้ปกติ แค่ดูสถิติเชิงลึกไม่ได้
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def write_env(values: dict[str, str]) -> None:
    """อัปเดต .env โดยไม่ทับค่าอื่นที่มีอยู่แล้ว"""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    remaining = dict(values)

    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in remaining.items())

    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="ขอ refresh token ของ YouTube")
    parser.add_argument("--channel", default="",
                        help="ช่องที่โทเค็นนี้เป็นของ (ว่าง = ช่องแรกที่ใช้ชื่อตัวแปรกลาง)")
    args = parser.parse_args()
    suffix = f"_{args.channel.upper()}" if args.channel else ""

    matches = glob.glob(str(ROOT / "client_secret*.json"))
    if not matches:
        print("ไม่พบไฟล์ client_secret*.json — ดาวน์โหลดจาก Google Cloud Console มาวางที่", ROOT)
        return 1

    if args.channel:
        print(f"ขอโทเค็นสำหรับช่อง {args.channel} — จะเขียนเป็น YT_*_{args.channel.upper()}\n")
    else:
        print("!! ไม่ได้ระบุ --channel จะเขียนทับโทเค็นของช่องแรก !!")
        if input("พิมพ์ yes ถ้าตั้งใจแบบนั้นจริง: ").strip().lower() != "yes":
            return 1

    print("กำลังเปิดเบราว์เซอร์ — เลือกบัญชี Gmail ที่เป็นเจ้าของช่อง YouTube ให้ถูกต้อง")
    print("ถ้าเจอหน้า 'Google hasn't verified this app' ให้กด Advanced แล้ว Go to ... (unsafe)")
    print("ซึ่งปลอดภัย เพราะแอปนี้คือแอปของคุณเอง\n")

    flow = InstalledAppFlow.from_client_secrets_file(matches[0], SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        print("ไม่ได้ refresh token กลับมา")
        print("ลองถอนสิทธิ์ที่ https://myaccount.google.com/permissions แล้วรันใหม่")
        return 1

    # บอกให้ชัดว่าโทเค็นที่เพิ่งได้เป็นของช่องไหน เพราะหน้าเลือกช่องของ Google
    # ขึ้นมาเร็วมากและกดผ่านง่าย ถ้าเลือกผิดจะไม่มีอะไรฟ้องเลยจนกว่าคลิปจะไปโผล่ผิดช่อง
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        actual = items[0]["snippet"]["title"] if items else "(ไม่พบช่อง)"
    except Exception as exc:  # noqa: BLE001 - เช็คไม่ได้ก็ยังเขียนโทเค็นให้
        actual = f"(ตรวจไม่ได้: {type(exc).__name__})"

    write_env({
        f"YT_CLIENT_ID{suffix}": creds.client_id,
        f"YT_CLIENT_SECRET{suffix}": creds.client_secret,
        f"YT_REFRESH_TOKEN{suffix}": creds.refresh_token,
    })

    print(f"\n>>> โทเค็นนี้เป็นของช่อง: {actual}")
    print(">>> ถ้าไม่ใช่ช่องที่ต้องการ ให้รันใหม่แล้วเลือกช่องให้ถูกตอนล็อกอิน\n")

    print("เขียนค่าลง .env เรียบร้อย (ไม่แสดงค่าออกหน้าจอโดยตั้งใจ)")
    for key, value in (("YT_CLIENT_ID", creds.client_id),
                       ("YT_CLIENT_SECRET", creds.client_secret),
                       ("YT_REFRESH_TOKEN", creds.refresh_token)):
        print(f"  {key + suffix:<28} {len(value)} ตัวอักษร")
    print("\nขั้นต่อไป: ลบไฟล์ client_secret*.json ทิ้ง แล้วเอาค่าทั้งสามไปใส่ใน")
    print("GitHub > Settings > Secrets and variables > Actions (ใช้ชื่อตามที่พิมพ์ข้างบน)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
