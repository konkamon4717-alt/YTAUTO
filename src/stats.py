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

REPORT = config.ROOT / "docs" / "channel.json"
ANALYTICS_SCOPES = ("yt-analytics.readonly", "yt-analytics-monetary.readonly")


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
            videos.append({
                "id": v["id"],
                "title": v["snippet"]["title"],
                "published": v["snippet"]["publishedAt"],
                "privacy": v.get("status", {}).get("privacyStatus"),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
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


def main() -> int:
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

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    c = data["channel"]
    print(f"  ช่อง        : {c['title']}")
    print(f"  ผู้ติดตาม    : {c['subscribers']:,}")
    print(f"  วิวรวม      : {c['views']:,}")
    print(f"  คลิปทั้งหมด : {c['videos']:,}")
    print(f"  ดึงรายคลิป  : {len(data['videos'])} คลิป")

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
