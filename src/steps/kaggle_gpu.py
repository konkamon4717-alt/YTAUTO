"""ตัวส่งงานไปรันบน GPU ฟรีของ Kaggle

Kaggle ไม่มี API แบบยิงแล้วได้ผลทันที ต้องทำเป็นรอบ ๆ แบบนี้
    push โน้ตบุ๊กขึ้นไป -> Kaggle เข้าคิวแล้วรัน -> เราคอยถาม status -> โหลดไฟล์ผลลัพธ์กลับมา

รอบหนึ่งกินเวลาหลายนาทีจากการติดตั้งของและโหลดโมเดล เพราะฉะนั้น
**ต้องส่งทุกช็อตของรอบนั้นไปพร้อมกันครั้งเดียว** ยิงทีละช็อตจะเสียเวลาโหลดโมเดลซ้ำทุกครั้ง
"""
import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

POLL_SECONDS = 20
DONE = {"complete", "error", "cancelAcknowledged", "cancelRequested"}


class KaggleError(RuntimeError):
    pass


def _env() -> dict:
    env = os.environ.copy()
    if not env.get("KAGGLE_USERNAME") or not env.get("KAGGLE_KEY"):
        raise KaggleError(
            "ไม่พบ KAGGLE_USERNAME / KAGGLE_KEY — ใส่ใน .env (เครื่องตัวเอง) "
            "หรือ Repository secrets (GitHub Actions)"
        )
    # ปิด output สีและ prompt ของ kaggle CLI เวลารันในระบบอัตโนมัติ
    env["KAGGLE_CONFIG_DIR"] = env.get("KAGGLE_CONFIG_DIR", str(Path.home() / ".kaggle"))
    return env


def _run(args: list[str], timeout: int = 600) -> str:
    result = subprocess.run(
        [str(Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "kaggle.exe")
         if os.name == "nt" else "kaggle", *args],
        capture_output=True, text=True, env=_env(), timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise KaggleError(f"kaggle {' '.join(args)} ล้มเหลว:\n{output.strip()[:800]}")
    return output


def write_metadata(folder: Path, slug: str, code_file: str,
                   dataset_sources: list[str] | None = None) -> None:
    """สร้าง kernel-metadata.json ที่ Kaggle ต้องการคู่กับไฟล์โค้ด"""
    username = os.environ.get("KAGGLE_USERNAME", "")
    meta = {
        "id": f"{username}/{slug}",
        "title": slug,
        "code_file": code_file,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": dataset_sources or [],
        "competition_sources": [],
        "kernel_sources": [],
    }
    (folder / "kernel-metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


def push(folder: Path) -> str:
    """ส่งโน้ตบุ๊กขึ้น Kaggle แล้วคืน slug ของงาน"""
    meta = json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))
    _run(["kernels", "push", "-p", str(folder)])
    return meta["id"]


def wait(slug: str, timeout_minutes: int = 45) -> str:
    """รอจนงานจบ คืนสถานะสุดท้าย"""
    deadline = time.time() + timeout_minutes * 60
    last = ""
    while time.time() < deadline:
        output = _run(["kernels", "status", slug]).lower()
        status = next((s for s in DONE if s.lower() in output), "")
        if status:
            return status
        state = "running" if "running" in output else "queued"
        if state != last:
            print(f"      Kaggle: {state}...")
            last = state
        time.sleep(POLL_SECONDS)
    raise KaggleError(f"งาน {slug} ไม่จบภายใน {timeout_minutes} นาที")


def fetch_output(slug: str, dest: Path) -> list[Path]:
    """ดึงไฟล์ผลลัพธ์กลับมา แล้วคืนรายการไฟล์ที่ได้"""
    dest.mkdir(parents=True, exist_ok=True)
    _run(["kernels", "output", slug, "-p", str(dest)])

    # ผลลัพธ์บางครั้งมาเป็น zip ก้อนเดียว แตกออกให้เรียบร้อย
    for archive in list(dest.glob("*.zip")):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        archive.unlink()

    return sorted(p for p in dest.rglob("*") if p.is_file())


def run_job(folder: Path, dest: Path, timeout_minutes: int = 45) -> list[Path]:
    """push -> รอ -> โหลดผลลัพธ์ ในขั้นตอนเดียว"""
    slug = push(folder)
    print(f"      ส่งงานขึ้น Kaggle แล้ว: {slug}")
    status = wait(slug, timeout_minutes)
    if status != "complete":
        log = _tail_log(slug, dest)
        raise KaggleError(f"งานจบด้วยสถานะ {status}\n{log}")
    return fetch_output(slug, dest)


def _tail_log(slug: str, dest: Path) -> str:
    """ดึง log ท้าย ๆ มาดูว่าพังเพราะอะไร"""
    try:
        logs = dest / "_log"
        shutil.rmtree(logs, ignore_errors=True)
        fetch_output(slug, logs)
        for path in logs.rglob("*.log"):
            return "\n".join(path.read_text(encoding="utf-8", errors="replace")
                             .splitlines()[-25:])
    except Exception:  # noqa: BLE001 - ดึง log ไม่ได้ก็ไม่ควรกลบ error เดิม
        pass
    return "(ดึง log ไม่ได้)"
