"""ดึงตัวเลขของช่องมาเก็บไว้ให้ห้องควบคุมอ่าน

  python -m src.stats

แบ่งเป็นสองชั้นตามสิทธิ์ที่ token มี:

  ชั้นพื้นฐาน (มีสิทธิ์อยู่แล้ว)
    ยอดซับ ยอดวิวรวม จำนวนคลิป และสถิติรายคลิป — ใช้ Data API ซึ่ง token ปัจจุบันเข้าถึงได้

  ชั้นวิเคราะห์ (ต้องขอสิทธิ์เพิ่ม)
    วิวรายวัน เวลาที่ดู ผู้ติดตามที่เพิ่ม และ "รายได้" — ใช้ Analytics API
    ต้องมี scope yt-analytics.readonly และ yt-analytics-monetary.readonly
    ถ้าไม่มีจะข้ามไปเงียบ ๆ ไม่ทำให้ทั้งคำสั่งล้ม

รายได้จะเป็น 0 เสมอจนกว่าช่องจะผ่าน YPP — ไม่ใช่บั๊ก แต่เป็นความจริงของช่องใหม่
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import config

KEEP_DAYS = 180
ANALYTICS_SCOPES = ("yt-analytics.readonly", "yt-analytics-monetary.readonly")


# ลักษณะของชื่อคลิปที่พอจะจับเป็นรูปแบบได้ ใช้ดูว่าแบบไหนคนกดเข้ามามากกว่า
# ไม่ใช่สถิติเชิงลึก แค่ติดป้ายให้คนมองเห็นรูปแบบเองได้เร็วขึ้น
TITLE_TRAITS = {
    "คำถาม": ("ไหม", "ทำไม", "อะไร", "หรือเปล่า", "?"),
    "ความขัดแย้ง": ("แต่", "กลับ", "ทั้งที่", "ไม่คิดว่า"),
    "ความถี่": ("ทุกวัน", "ทุกคืน", "ทุกเดือน", "ทุกเช้า", "ตลอด"),
    "ความลับ": ("ความลับ", "เบื้องหลัง", "ซ่อน", "ไม่มีใครรู้"),
    "อารมณ์แรง": ("!", "พูดไม่ออก", "น้ำตา", "ช็อก", "ตะลึง"),
}


def title_traits(title: str) -> list[str]:
    return [name for name, words in TITLE_TRAITS.items()
            if any(w in title for w in words)]


def _days_since(iso: str) -> float:
    from datetime import datetime, timezone
    published = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max((datetime.now(timezone.utc) - published).total_seconds() / 86400, 0.25)


def basic(youtube) -> dict:
    """ตัวเลขรวมของช่อง + สถิติรายคลิป"""
    channels = youtube.channels().list(
        part="snippet,statistics,contentDetails", mine=True).execute()
    items = channels.get("items", [])
    if not items:
        raise RuntimeError("ไม่พบช่องในบัญชีนี้")

    channel = items[0]
    stats = channel.get("statistics", {})
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    # ดึงรายการคลิปล่าสุด แล้วขอสถิติเป็นชุดเดียว (ถูกกว่าถามทีละคลิป)
    playlist = youtube.playlistItems().list(
        part="contentDetails", playlistId=uploads, maxResults=25).execute()
    video_ids = [i["contentDetails"]["videoId"] for i in playlist.get("items", [])]

    videos = []
    if video_ids:
        detail = youtube.videos().list(
            part="snippet,statistics,status", id=",".join(video_ids)).execute()
        for v in detail.get("items", []):
            s = v.get("statistics", {})
            views = int(s.get("viewCount", 0))
            likes = int(s.get("likeCount", 0))
            title = v["snippet"]["title"]
            days = _days_since(v["snippet"]["publishedAt"])
            videos.append({
                "id": v["id"],
                "title": title,
                "published": v["snippet"]["publishedAt"],
                "privacy": v.get("status", {}).get("privacyStatus"),
                "views": views,
                "likes": likes,
                "comments": int(s.get("commentCount", 0)),
                # คลิปเก่ามีเวลาสะสมวิวมากกว่า ต้องหารด้วยอายุถึงจะเทียบกันได้
                "views_per_day": round(views / days, 1),
                "like_rate": round(likes / views * 100, 2) if views else 0.0,
                "traits": title_traits(title),
                "days": round(days, 1),
            })

    return {
        "channel": {
            "title": channel["snippet"]["title"],
            "id": channel["id"],
            "subscribers": int(stats.get("subscriberCount", 0)),
            "views": int(stats.get("viewCount", 0)),
            "videos": int(stats.get("videoCount", 0)),
        },
        "videos": videos,
    }


def analytics(creds, channel_id: str) -> dict | None:
    """วิวรายวัน เวลาที่ดู และรายได้ — ต้องมีสิทธิ์เพิ่ม ถ้าไม่มีคืน None"""
    granted = set(creds.scopes or [])
    if not any(s in scope for scope in granted for s in ANALYTICS_SCOPES):
        return None

    from googleapiclient.discovery import build
    api = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    end = date.today()
    start = end - timedelta(days=28)
    metrics = ("views,estimatedMinutesWatched,averageViewDuration,"
               "subscribersGained,subscribersLost")

    try:
        report = api.reports().query(
            ids=f"channel=={channel_id}", startDate=str(start), endDate=str(end),
            metrics=metrics, dimensions="day", sort="day").execute()
    except Exception as exc:  # noqa: BLE001 - ไม่มีสิทธิ์หรือช่องยังไม่มีข้อมูล
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    headers = [h["name"] for h in report.get("columnHeaders", [])]
    rows = [dict(zip(headers, r)) for r in report.get("rows", [])]

    money = None
    try:
        rev = api.reports().query(
            ids=f"channel=={channel_id}", startDate=str(start), endDate=str(end),
            metrics="estimatedRevenue,cpm").execute()
        rev_rows = rev.get("rows") or [[0, 0]]
        money = {"estimated_revenue_usd": rev_rows[0][0], "cpm": rev_rows[0][1]}
    except Exception as exc:  # noqa: BLE001 - ช่องที่ยังไม่เข้า YPP จะถูกปฏิเสธที่นี่
        money = {"unavailable": str(exc)[:140]}

    return {"period": {"start": str(start), "end": str(end)},
            "daily": rows, "revenue": money}


def snapshot(data: dict) -> list[dict]:
    """จดตัวเลขของวันนี้ต่อท้ายไว้ เพื่อให้มีเส้นการเติบโตโดยไม่ต้องขอสิทธิ์เพิ่ม

    Analytics API ให้วิวรายวันอยู่แล้ว แต่ต้องขอ scope เพิ่มแล้วออก token ใหม่
    ระหว่างที่ยังไม่ได้ทำ แค่จดยอดรวมไว้วันละครั้งก็พอเห็นการเติบโตจริง
    และต่อให้ขอสิทธิ์ได้ทีหลัง ตัวนี้ก็ยังมีค่าเพราะเก็บยอดรายคลิปไว้ด้วย

    ที่ต้องเริ่มวันนี้เพราะย้อนกลับไปเก็บของเมื่อวานไม่ได้ — ไม่มีใครเก็บไว้ให้
    """
    growth = config.docs_dir() / "growth.json"
    rows = []
    if growth.exists():
        try:
            rows = json.loads(growth.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []   # ไฟล์พังไม่ควรทำให้ทั้งคำสั่งล้ม ยอมเสียประวัติดีกว่าเสียคลิป

    c = data["channel"]
    today = date.today().isoformat()
    row = {
        "date": today,
        "subscribers": c["subscribers"],
        "views": c["views"],
        "videos": c["videos"],
        # เก็บรายคลิปไว้ด้วย จะได้ดูทีหลังได้ว่าคลิปไหนยังมีคนดูอยู่ ไม่ใช่ตายไปแล้ว
        "per_video": {v["id"]: v["views"] for v in data["videos"]},
    }

    # วันเดียวกันให้ทับของเดิม รันซ้ำกี่ครั้งก็ได้วันละแถว
    rows = [r for r in rows if r.get("date") != today] + [row]
    rows.sort(key=lambda r: r["date"])
    return rows[-KEEP_DAYS:]


def main(argv: list[str] | None = None) -> int:
    import argparse
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--channel", help="ช่องที่จะดึงตัวเลข")
    config.use(args.parse_args(argv).channel)

    from .steps import upload

    cfg = config.load()
    youtube = upload.client()
    data = basic(youtube)

    # ใช้ credential ตัวเดิมต่อ ไม่ต้องขอใหม่
    creds = youtube._http.credentials if hasattr(youtube, "_http") else None
    if creds is None:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None, refresh_token=config.secret("YT_REFRESH_TOKEN"),
            client_id=config.secret("YT_CLIENT_ID"),
            client_secret=config.secret("YT_CLIENT_SECRET"),
            token_uri=upload.TOKEN_URI, scopes=upload.SCOPES)
        creds.refresh(Request())

    data["analytics"] = analytics(creds, data["channel"]["id"])
    data["fetched_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(timespec="seconds")

    docs = config.docs_dir()
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "channel.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = snapshot(data)
    (docs / "growth.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    c = data["channel"]
    print(f"  ช่อง        : {c['title']}")
    print(f"  ผู้ติดตาม    : {c['subscribers']:,}")
    print(f"  วิวรวม      : {c['views']:,}")
    print(f"  คลิปทั้งหมด : {c['videos']:,}")
    print(f"  ดึงรายคลิป  : {len(data['videos'])} คลิป")
    print(f"  ประวัติสะสม : {len(rows)} วัน")

    if data["analytics"] is None:
        print("\n  ยังดู Analytics ไม่ได้ — token ไม่มีสิทธิ์ yt-analytics")
        print("  ขอ token ใหม่ด้วย python tools/get_refresh_token.py เพื่อเพิ่มสิทธิ์")
    elif "error" in data["analytics"]:
        print(f"\n  Analytics ตอบกลับผิดพลาด: {data['analytics']['error'][:110]}")
    else:
        rev = data["analytics"].get("revenue") or {}
        if "unavailable" in rev:
            print("\n  รายได้: ยังดูไม่ได้ (ช่องยังไม่ผ่าน YPP)")
        else:
            print(f"\n  รายได้ประมาณ 28 วัน: ${rev.get('estimated_revenue_usd', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
