@echo off
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto nodir
where git >nul 2>nul
if errorlevel 1 goto nogit
set OLD=
set NEW=
for /f %%i in ('git rev-parse HEAD') do set OLD=%%i
echo Dang cap nhat LendLand Pro: git pull origin main
echo.
git pull origin main
if errorlevel 1 goto fail
for /f %%i in ('git rev-parse HEAD') do set NEW=%%i
echo.
if "%OLD%"=="%NEW%" goto same
echo ===== DA CO THAY DOI MOI =====
echo.
echo --- Cac ban cap nhat, moi nhat o tren ---
git log --oneline --no-decorate %OLD%..%NEW%
echo.
echo --- Cac tep da thay doi ---
git diff --stat %OLD% %NEW%
echo.
echo Neu may chu dang chay: tat bang Ctrl+C roi bam doi chay-may-chu.bat de chay ban moi.
goto end
:same
echo ===== KHONG CO THAY DOI: dang la ban moi nhat =====
goto end
:fail
echo.
echo ===== CAP NHAT KHONG THANH CONG. Xem thong bao loi phia tren. =====
echo Neu bao thu muc chua phai kho Git hoac co thay doi cuc bo xung dot, gui nguyen thong bao cho nguoi ho tro.
goto end
:nodir
echo Khong vao duoc thu muc LendLand Pro.
goto end
:nogit
echo Chua cai Git hoac Git chua co trong PATH. Cai Git for Windows roi thu lai.
:end
echo.
echo Bam phim bat ky de dong cua so nay.
pause >nul
