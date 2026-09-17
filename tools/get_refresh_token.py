"""ขอ refresh token ของ YouTube ครั้งเดียว แล้วเขียนลง .env ให้เลย

วิธีใช้:
  1. ดาวน์โหลดไฟล์ client_secret_*.json จาก Google Cloud Console มาไว้โฟลเดอร์โปรเจกต์
  2. python tools/get_refresh_token.py
  3. เบราว์เซอร์จะเปิดให้ล็อกอิน เลือกบัญชีและช่องที่จะอัปโหลด
  4. สคริปต์เขียนค่าลง .env ให้เอง

สคริปต์นี้ "ไม่พิมพ์ค่า token ออกหน้าจอ" โดยตั้งใจ เพราะอะไรที่ถูกพิมพ์ออกมา
จะไปติดอยู่ใน log ของเทอร์มินัล ประวัติการรัน และหน้าต่างแชทที่เปิดดูอยู่

ก่อนรัน ให้แน่ใจว่า OAuth consent screen อยู่สถานะ "In production" แล้ว
ถ้ายังเป็น Testing อยู่ token ที่ได้จะหมดอายุใน 7 วัน
"""
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
    matches = glob.glob(str(ROOT / "client_secret*.json"))
    if not matches:
        print("ไม่พบไฟล์ client_secret*.json — ดาวน์โหลดจาก Google Cloud Console มาวางที่", ROOT)
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

    write_env({
        "YT_CLIENT_ID": creds.client_id,
        "YT_CLIENT_SECRET": creds.client_secret,
        "YT_REFRESH_TOKEN": creds.refresh_token,
    })

    print("\nเขียนค่าลง .env เรียบร้อย (ไม่แสดงค่าออกหน้าจอโดยตั้งใจ)")
    print(f"  YT_CLIENT_ID      {len(creds.client_id)} ตัวอักษร")
    print(f"  YT_CLIENT_SECRET  {len(creds.client_secret)} ตัวอักษร")
    print(f"  YT_REFRESH_TOKEN  {len(creds.refresh_token)} ตัวอักษร")
    print("\nขั้นต่อไป: ลบไฟล์ client_secret*.json ทิ้ง แล้วเอาค่าทั้งสามไปใส่ใน")
    print("GitHub > Settings > Secrets and variables > Actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
