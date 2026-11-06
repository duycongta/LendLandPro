@echo off
chcp 65001 >nul
cd /d "%~dp0" || (echo Khong vao duoc thu muc LendLand Pro & pause & exit /b 1)
where git >nul 2>nul || (echo Chua cai Git hoac Git chua co trong PATH. Cai Git for Windows roi thu lai. & pause & exit /b 1)
echo Dang cap nhat LendLand Pro (git pull origin main)...
echo.
git pull origin main
if errorlevel 1 (
  echo.
  echo CAP NHAT KHONG THANH CONG. Xem thong bao loi phia tren.
  echo Neu bao thu muc chua phai kho Git hoac co thay doi cuc bo, gui nguyen thong bao cho nguoi ho tro.
) else (
  echo.
  echo Da cap nhat xong. Neu may chu dang chay, hay tat (Ctrl+C) roi bam doi chay-may-chu.bat de chay ban moi.
)
echo.
pause
