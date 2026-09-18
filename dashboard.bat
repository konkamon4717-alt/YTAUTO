@echo off
chcp 65001 >nul
title ห้องควบคุม nithan1min
cd /d "%~dp0"

echo.
echo   ห้องควบคุม nithan1min
echo   ---------------------------------------------
echo.

if not exist ".venv\Scripts\python.exe" (
    echo   [!] ไม่พบ .venv — ยังไม่ได้ติดตั้ง
    echo       รัน: python -m venv .venv
    echo            .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo   กำลังเปิด... เบราว์เซอร์จะเปิดให้เอง
echo   ปิดหน้าต่างนี้เมื่อไหร่ ห้องควบคุมจะดับ
echo.

.venv\Scripts\python.exe -m src.dashboard

echo.
echo   ห้องควบคุมปิดแล้ว
pause
