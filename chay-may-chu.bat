@echo off
cd /d "%~dp0server" || (echo Khong tim thay thu muc server & pause & exit /b 1)
python -c "import uvicorn, fastapi, requests, bs4, openpyxl, jinja2, multipart" >nul 2>&1
if errorlevel 1 goto cai
goto chay

:cai
echo Lan dau tren may nay: dang cai thu vien Python (can Internet, mat vai phut)...
python -m pip install -r requirements.txt
if errorlevel 1 goto loi_cai

:chay
echo Dang chay may chu khao gia tai http://localhost:8000  (nhan Ctrl+C de dung)
python -m uvicorn app.main:app --port 8000
echo.
echo May chu da dung hoac gap loi (xem dong thong bao phia tren).
pause
exit /b 0

:loi_cai
echo.
echo Cai thu vien that bai. Kiem tra Internet, hoac chay tay: python -m pip install -r server\requirements.txt
pause
exit /b 1
