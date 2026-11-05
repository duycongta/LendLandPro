@echo off
cd /d "%~dp0server" || (echo Khong tim thay thu muc server & pause & exit /b 1)
echo Dang chay may chu khao gia tai http://localhost:8000  (nhan Ctrl+C de dung)
python -m uvicorn app.main:app --port 8000
echo.
echo May chu da dung hoac gap loi (xem dong thong bao phia tren).
pause
