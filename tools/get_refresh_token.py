"""ขอ refresh token ของ YouTube ครั้งเดียว แล้วเอาไปใส่ GitHub Secrets

วิธีใช้:
  1. ดาวน์โหลดไฟล์ client_secret_*.json จาก Google Cloud Console มาไว้โฟลเดอร์นี้
  2. python tools/get_refresh_token.py
  3. เบราว์เซอร์จะเปิดให้ล็อกอิน เลือกช่องที่จะอัปโหลด
  4. คัดลอกค่าที่พิมพ์ออกมาไปใส่ Secrets

ค่าที่ได้เป็นความลับระดับเดียวกับรหัสผ่าน อย่าวางในแชท อย่า commit ลง git
"""
import glob
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    matches = glob.glob(str(ROOT / "client_secret*.json"))
    if not matches:
        print("ไม่พบไฟล์ client_secret*.json — ดาวน์โหลดจาก Google Cloud Console มาวางที่", ROOT)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(matches[0], SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        print("ไม่ได้ refresh token กลับมา — ลองถอนสิทธิ์ที่ myaccount.google.com/permissions แล้วรันใหม่")
        return 1

    print("\n" + "=" * 60)
    print("เอาสามค่านี้ไปใส่ GitHub > Settings > Secrets and variables > Actions")
    print("=" * 60)
    print(f"YT_CLIENT_ID     = {creds.client_id}")
    print(f"YT_CLIENT_SECRET = {creds.client_secret}")
    print(f"YT_REFRESH_TOKEN = {creds.refresh_token}")
    print("=" * 60)
    print("ใส่เสร็จแล้วลบไฟล์ client_secret*.json ออกจากโฟลเดอร์นี้ด้วย")
    return 0


if __name__ == "__main__":
    sys.exit(main())
