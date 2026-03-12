@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM ============================================================
REM Portfoljindex - run.bat (scheduler-friendly)
REM - Kor src.main och sedan src.dashboard_prep i projektets .venv
REM - Loggar till logs\run_YYYYMMDD_HHMMSS.log (bredvid .bat)
REM - Ingen PAUSE (bra for automation)
REM ============================================================

REM Sakerstall att vi kor fran projektroten (dar .bat ligger)
cd /d "%~dp0"

REM Skapa loggmapp
set "LOG_DIR=%~dp0logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Timestamp (Windows-kompatibel)
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do (
  set "D1=%%a"
  set "D2=%%b"
  set "D3=%%c"
)
for /f "tokens=1-3 delims=:.," %%a in ("%time%") do (
  set "T1=%%a"
  set "T2=%%b"
  set "T3=%%c"
)

REM Nollstall ev. ledande blank i timmen (t.ex. " 9")
set "T1=%T1: =0%"

REM Bygg filnamn: run_YYYYMMDD_HHMMSS.log
set "LOG_FILE=%LOG_DIR%\run_%D3%%D2%%D1%_%T1%%T2%%T3%.log"

echo ============================================================ > "%LOG_FILE%"
echo Start: %date% %time%>> "%LOG_FILE%"
echo Working dir: %CD%>> "%LOG_FILE%"
echo ============================================================>> "%LOG_FILE%"

REM Aktivera venv
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat" >> "%LOG_FILE%" 2>&1
) else (
  echo ERROR: Hittar ingen .venv\Scripts\activate.bat i %CD%>> "%LOG_FILE%"
  echo Kontrollera att venv heter ".venv" och ligger i projektroten.>> "%LOG_FILE%"
  exit /b 1
)

REM Kor Portfolio_index
echo Running: py -m src.main>> "%LOG_FILE%"
py -m src.main >> "%LOG_FILE%" 2>&1
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" goto :finish

REM Kor Dashboard_prep
echo Running: py -m src.dashboard_prep>> "%LOG_FILE%"
py -m src.dashboard_prep >> "%LOG_FILE%" 2>&1
set "ERR=%ERRORLEVEL%"

:finish
REM Avaktivera venv om deactivate finns
if defined VIRTUAL_ENV (
  deactivate >> "%LOG_FILE%" 2>&1
)

echo ============================================================>> "%LOG_FILE%"
echo End: %date% %time%>> "%LOG_FILE%"
echo Exit code: %ERR%>> "%LOG_FILE%"
echo Log: %LOG_FILE%>> "%LOG_FILE%"
echo ============================================================>> "%LOG_FILE%"

exit /b %ERR%
