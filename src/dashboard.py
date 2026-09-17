"""เปิดห้องควบคุมในเครื่อง

  python -m src.dashboard

หน้าเว็บกับไฟล์สถานะต้องอยู่โดเมนเดียวกัน ไม่งั้นเบราว์เซอร์จะบล็อกการอ่านไฟล์ (CORS)
เปิดไฟล์ตรง ๆ ด้วย file:// ก็ไม่ได้ด้วยเหตุผลเดียวกัน จึงต้องมีเซิร์ฟเวอร์เล็ก ๆ ครอบ

ไฟล์เดียวกันนี้เสิร์ฟผ่าน GitHub Pages ได้เลยโดยไม่ต้องแก้อะไร
"""
import argparse
import http.server
import socketserver
import threading
import webbrowser
from functools import partial

from .config import ROOT

DOCS = ROOT / "docs"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # ไฟล์สถานะเปลี่ยนตลอด ห้ามให้เบราว์เซอร์แคช ไม่งั้นจะเห็นของเก่า
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

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

    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
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
