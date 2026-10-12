"""เติมประวัติให้ตรงกับคลิปที่อยู่บนช่องจริง

  python tools/sync_history.py --channel world
  python tools/sync_history.py --channel world --apply

ปกติ pipeline จดประวัติเองทุกรอบ แต่การจดนั้นจะมีผลก็ต่อเมื่อ commit กลับ
ขึ้น repo สำเร็จ ถ้าขั้นตอนนั้นล้ม ประวัติจะหายไปโดยที่คลิปขึ้นช่องไปแล้ว
ผลคือ AI ไม่รู้ว่าเคยเล่าเรื่องอะไรไปแล้ว แล้วเขียนเรื่องเดิมซ้ำ
ซึ่งเกิดขึ้นจริงมาแล้วหกคลิปติดกัน

สคริปต์นี้อ่านคลิปที่อยู่บนช่องจริงแล้วเติมตัวที่ขาดเข้าไปในประวัติ
ใช้ตอนรู้ตัวว่าประวัติหลุด ไม่ใช่ของที่ต้องรันประจำ

ไม่ใส่ --apply จะแค่บอกว่าจะเติมอะไรบ้าง ไม่เขียนไฟล์
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, help="ช่องที่จะเติมประวัติให้")
    parser.add_argument("--apply", action="store_true", help="เขียนไฟล์จริง")
    args = parser.parse_args()
    config.use(args.channel)

    from src.steps import upload
    yt = upload.client()
    uploads = yt.channels().list(part="contentDetails", mine=True).execute()
    playlist = uploads["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items, page = [], None
    while True:
        batch = yt.playlistItems().list(part="snippet", playlistId=playlist,
                                        maxResults=50, pageToken=page).execute()
        items += batch.get("items", [])
        page = batch.get("nextPageToken")
        if not page:
            break

    data = state.load()
    known = {v.get("video_id") for v in data["published"]}

    missing = [i for i in items if i["snippet"]["resourceId"]["videoId"] not in known]
    if not missing:
        print("ประวัติตรงกับช่องอยู่แล้ว ไม่มีอะไรต้องเติม")
        return 0

    print(f"ขาดไป {len(missing)} คลิป:")
    for item in sorted(missing, key=lambda i: i["snippet"]["publishedAt"]):
        snippet = item["snippet"]
        title = snippet["title"]
        print(f"  + {snippet['publishedAt'][:10]}  {title[:60]}")
        if args.apply:
            # ใช้ชื่อคลิปเป็นเรื่องย่อ เพราะเรื่องย่อตัวจริงหายไปพร้อมกับประวัติ
            # ไม่สมบูรณ์เท่าของเดิมแต่พอให้ AI รู้ว่าเล่าเรื่องนี้ไปแล้ว ซึ่งคือหน้าที่เดียวของมัน
            data["premises"].append(title)
            data["published"].append({
                "ok": True,
                "title": title,
                "premise": title,
                "video_id": snippet["resourceId"]["videoId"],
                "at": snippet["publishedAt"],
                "recovered": True,
            })

    if not args.apply:
        print("\n(ยังไม่ได้เขียนไฟล์ — ใส่ --apply ถ้าจะเติมจริง)")
        return 0

    data["published"].sort(key=lambda v: v.get("at", ""))
    state.save(data)
    print(f"\nเติมแล้ว ประวัติตอนนี้มี {len(data['published'])} คลิป")
    return 0


if __name__ == "__main__":
    sys.exit(main())
