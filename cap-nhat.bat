@echo off
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto nodir
if "%LLP_SELFUPD%"=="1" goto afterself
if exist ".git" goto afterself
goto selfupd
:afterself
if not exist ".git" goto zip
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
:selfupd
echo Kiem tra file cap-nhat.bat / chay-may-chu.bat moi tren GitHub...
set LLPT=%TEMP%\llp_bat
rmdir /s /q "%LLPT%" >nul 2>nul
mkdir "%LLPT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $u='https://raw.githubusercontent.com/duycongta/lendlandpro/main/'; try { foreach($f in 'cap-nhat.bat','chay-may-chu.bat'){ Invoke-WebRequest -UseBasicParsing ($u+$f+'?t='+[guid]::NewGuid()) -OutFile ('%LLPT%\'+$f) }; exit 0 } catch { exit 1 }" >nul 2>nul
if errorlevel 1 goto selfskip
if not exist "%LLPT%\cap-nhat.bat" goto selfskip
if not exist "%LLPT%\chay-may-chu.bat" goto selfskip
fc /b "%LLPT%\chay-may-chu.bat" "%~dp0chay-may-chu.bat" >nul 2>nul
if errorlevel 1 copy /y "%LLPT%\chay-may-chu.bat" "%~dp0chay-may-chu.bat" >nul & echo Da cap nhat chay-may-chu.bat
fc /b "%LLPT%\cap-nhat.bat" "%~f0" >nul 2>nul
if errorlevel 1 goto selfswap
echo File .bat da la ban moi nhat.
goto selfskip
:selfswap
echo Co ban cap-nhat.bat moi: dang thay va chay lai ban moi...
copy /y "%LLPT%\cap-nhat.bat" "%~f0" >nul & set LLP_SELFUPD=1& cmd /c ""%~f0"" & exit /b
:selfskip
rmdir /s /q "%LLPT%" >nul 2>nul
goto afterself

:zip
echo Thu muc nay khong phai kho Git (tai bang file zip). Chuyen sang cap nhat bang cach tai zip moi nhat tu GitHub.
echo Du lieu da luu trong server\data duoc giu nguyen.
echo.
set TMPD=%TEMP%\llp_update
rmdir /s /q "%TMPD%" >nul 2>nul
mkdir "%TMPD%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing 'https://github.com/duycongta/lendlandpro/archive/refs/heads/main.zip' -OutFile '%TMPD%\m.zip'; Expand-Archive -Force '%TMPD%\m.zip' '%TMPD%\x'; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto zipfail
if not exist "%TMPD%\x\lendlandpro-main\index.html" goto zipfail
robocopy "%TMPD%\x\lendlandpro-main" "%CD%" /E /XD "%TMPD%\x\lendlandpro-main\server\data" "%TMPD%\x\lendlandpro-main\.git" /NFL /NDL /NJH /NJS /NP >nul
robocopy "%TMPD%\x\lendlandpro-main\server\data" "%CD%\server\data" /E /XC /XN /XO /NFL /NDL /NJH /NJS /NP >nul
rmdir /s /q "%TMPD%" >nul 2>nul
echo ===== DA CAP NHAT BANG ZIP: dang la ban moi nhat tren GitHub =====
echo Neu may chu dang chay: tat bang Ctrl+C roi bam doi chay-may-chu.bat de chay ban moi.
goto end
:zipfail
echo.
echo ===== TAI ZIP KHONG THANH CONG. Kiem tra Internet roi thu lai. =====
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
