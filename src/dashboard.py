"""ห้องควบคุม — เสิร์ฟหน้าเว็บ + สั่งงานได้จริง

  python -m src.dashboard

หน้าเว็บกับไฟล์สถานะต้องอยู่โดเมนเดียวกัน ไม่งั้นเบราว์เซอร์บล็อกการอ่านไฟล์ (CORS)
และเปิดด้วย file:// ก็ไม่ได้ด้วยเหตุผลเดียวกัน จึงต้องมีเซิร์ฟเวอร์เล็ก ๆ ครอบ

เซิร์ฟเวอร์นี้รันบนเครื่องเราจึง "สั่งงานได้จริง" ต่างจากตอนขึ้น GitHub Pages
ที่เป็นไฟล์นิ่ง ๆ อ่านได้อย่างเดียว หน้าเว็บตรวจเองว่าอยู่โหมดไหนแล้วซ่อนปุ่มให้

ผูกกับ 127.0.0.1 เท่านั้น ไม่เปิดออกเน็ต เพราะปุ่มพวกนี้สั่งรันโปรแกรมได้
"""
import argparse
import http.server
import json
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from functools import partial
from pathlib import Path

from .config import OUT, ROOT

DOCS = ROOT / "docs"
MAX_LOG_LINES = 400


class Job:
    """งานที่กำลังรันอยู่ ครั้งละงานเดียวเท่านั้น"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.name = ""
        self.started = 0.0
        self.log: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self.exit_code: int | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, name: str, args: list[str]) -> tuple[bool, str]:
        with self.lock:
            if self.running:
                return False, f"กำลังรัน '{self.name}' อยู่ รอให้เสร็จก่อน"

            self.name = name
            self.started = time.time()
            self.exit_code = None
            self.log.clear()
            self.log.append(f"$ {' '.join(args[-4:])}")

            self.process = subprocess.Popen(
                [sys.executable, *args], cwd=str(ROOT),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            threading.Thread(target=self._pump, daemon=True).start()
            return True, f"เริ่ม '{name}' แล้ว"

    def _pump(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.log.append(line.rstrip())
        self.exit_code = self.process.wait()
        self.log.append(f"— จบแล้ว (exit {self.exit_code}) —")

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "name": self.name,
            "seconds": round(time.time() - self.started) if self.started else 0,
            "exit_code": self.exit_code,
            "log": list(self.log),
        }


JOB = Job()

# ปุ่มบนหน้าเว็บ -> คำสั่งที่จะรันจริง
COMMANDS = {
    "test":    ("ทดลองสร้าง (ไม่อัปโหลด)", ["-m", "src.pipeline", "--count", "1", "--no-upload", "--keep"]),
    "publish": ("สร้างและอัปโหลด",         ["-m", "src.pipeline", "--count", "1"]),
    "health":  ("ตรวจสุขภาพบริการ",        ["-m", "src.health"]),
    "stats":   ("ดึงตัวเลขช่อง",            ["-m", "src.stats"]),
    "music":   ("สร้างเสียงคลอใหม่",        ["tools/make_music.py"]),
}


def latest_clip() -> Path | None:
    """คลิปล่าสุดที่ยังเหลืออยู่ในโฟลเดอร์ผลลัพธ์"""
    clips = sorted(OUT.glob("*/final.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return clips[0] if clips else None


class Handler(http.server.SimpleHTTPRequestHandler):

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - ชื่อตามที่ base class กำหนด
        if self.path.startswith("/api/state"):
            clip = latest_clip()
            return self._json({
                "local": True,
                "job": JOB.snapshot(),
                "commands": {k: v[0] for k, v in COMMANDS.items()},
                "clip": f"/api/clip?t={int(clip.stat().st_mtime)}" if clip else None,
                "clip_name": clip.parent.name if clip else None,
            })

        if self.path.startswith("/api/clip"):
            clip = latest_clip()
            if not clip:
                return self._json({"error": "ยังไม่มีคลิป"}, 404)
            data = clip.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/run/"):
            return self._json({"error": "ไม่รู้จักคำสั่งนี้"}, 404)

        key = self.path.rsplit("/", 1)[-1].split("?")[0]
        if key not in COMMANDS:
            return self._json({"error": f"ไม่รู้จักคำสั่ง {key}"}, 400)

        label, args = COMMANDS[key]
        ok, message = JOB.start(label, args)
        return self._json({"ok": ok, "message": message}, 200 if ok else 409)

    def end_headers(self) -> None:
        # ไฟล์สถานะเปลี่ยนตลอด ห้ามให้เบราว์เซอร์แคช ไม่งั้นจะเห็นของเก่า
        if "Cache-Control" not in self._headers_buffer_keys():
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def _headers_buffer_keys(self) -> set[str]:
        return {h.split(b":")[0].decode("latin-1")
                for h in getattr(self, "_headers_buffer", []) if b":" in h}

    def log_message(self, fmt: str, *args) -> None:
        pass  # ไม่ต้องรก ๆ ทุก request


def main() -> int:
    parser = argparse.ArgumentParser(description="เปิดห้องควบคุมในเครื่อง")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--no-open", action="store_true", help="ไม่ต้องเปิดเบราว์เซอร์ให้")
    args = parser.parse_args()

    if not (DOCS / "index.html").exists():
        print("ไม่พบ docs/index.html")
        return 1

    handler = partial(Handler, directory=str(DOCS))
    socketserver.TCPServer.allow_reuse_address = True

    # 127.0.0.1 เท่านั้น ปุ่มในหน้านี้สั่งรันโปรแกรมได้ ห้ามเปิดออกเน็ตเด็ดขาด
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"ห้องควบคุมเปิดที่ {url}")
        print("กด Ctrl+C เพื่อปิด")
        if not args.no_open:
            threading.Timer(0.6, webbrowser.open, args=(url,)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nปิดแล้ว")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
