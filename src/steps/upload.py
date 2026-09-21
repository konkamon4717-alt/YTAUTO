"""อัปโหลดขึ้น YouTube ด้วย Data API v3 (ใช้ refresh token ไม่ต้องล็อกอินใหม่ทุกครั้ง)"""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import secret

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def client():
    creds = Credentials(
        token=None,
        refresh_token=secret("YT_REFRESH_TOKEN"),
        client_id=secret("YT_CLIENT_ID"),
        client_secret=secret("YT_CLIENT_SECRET"),
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video_path: Path, story: dict, cfg: dict) -> str:
    youtube = client()
    up = cfg["upload"]

    tags = [t.lstrip("#") for t in story.get("hashtags", [])][:15]
    hashtag_line = " ".join(f"#{t}" for t in tags[:5])
    description = f"{story['description']}\n\n{hashtag_line}\n#shorts"

    body = {
        "snippet": {
            "title": story["title"][:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": str(up["category_id"]),
            "defaultLanguage": cfg["channel"]["language"],
            "defaultAudioLanguage": cfg["channel"]["language"],
        },
        "status": {
            "privacyStatus": up["privacy"],
            "selfDeclaredMadeForKids": bool(up["made_for_kids"]),
            "containsSyntheticMedia": bool(up.get("self_declared_ai", True)),
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4",
                            chunksize=4 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    _add_localizations(youtube, video_id, story, cfg)
    _set_thumbnail(youtube, video_id, cfg)
    return video_id


def _set_thumbnail(youtube, video_id: str, cfg: dict) -> None:
    """อัปปกที่สร้างไว้ ถ้ามี — ต้องยืนยันเบอร์โทรในช่องก่อนถึงจะใช้ได้"""
    cover = cfg.get("_thumbnail")
    if not cover or not Path(cover).exists():
        return
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(cover), mimetype="image/jpeg"),
        ).execute()
        print("      ใส่ปกคลิปแล้ว")
    except Exception as exc:  # noqa: BLE001 - ปกล้มไม่ควรทำให้คลิปที่อัปแล้วนับว่าพัง
        print(f"[warn] ใส่ปกไม่สำเร็จ: {str(exc)[:160]}")


def _add_localizations(youtube, video_id: str, story: dict, cfg: dict) -> None:
    """ใส่ชื่อ/คำอธิบายหลายภาษา ช่วยให้คนต่างประเทศเจอคลิป"""
    wanted = set(cfg["upload"].get("localizations", []))
    entries = {
        item["lang"]: {"title": item["title"][:100],
                       "description": item["description"][:5000]}
        for item in story.get("localizations", [])
        if item.get("lang") in wanted
    }
    if not entries:
        return

    try:
        youtube.videos().update(
            part="localizations",
            body={"id": video_id, "localizations": entries},
        ).execute()
    except Exception as exc:  # noqa: BLE001 - ล้มตรงนี้ไม่ควรทำให้คลิปที่อัปแล้วนับเป็นพัง
        print(f"[warn] ใส่ localizations ไม่สำเร็จ: {exc}")
