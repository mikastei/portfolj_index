@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM ============================================================
REM Portfoljindex - run.bat (scheduler-friendly)
REM - Kor src.main och sedan src.bi_prep i projektets .venv
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

REM Kor BI_prep
echo Running: py -m src.bi_prep>> "%LOG_FILE%"
py -m src.bi_prep >> "%LOG_FILE%" 2>&1
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" goto :finish

REM Best-effort: oppna och spara BI-workbooken i riktig Excel for att minska
REM kompatibilitetsproblem vid direkt uppdatering i Power BI efter Python-export.
if exist "data\portfolio_bi_data.xlsx" (
  echo Running: normalize data\portfolio_bi_data.xlsx via Excel COM>> "%LOG_FILE%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$path = Join-Path (Get-Location) 'data\portfolio_bi_data.xlsx';" ^
    "$excel = $null; $workbook = $null;" ^
    "try {" ^
    "  $excel = New-Object -ComObject Excel.Application;" ^
    "  $excel.Visible = $false;" ^
    "  $excel.DisplayAlerts = $false;" ^
    "  $workbook = $excel.Workbooks.Open($path);" ^
    "  $workbook.Save();" ^
    "  $workbook.Close($false);" ^
    "  Write-Output 'BI workbook normalized via Excel COM';" ^
    "} catch {" ^
    "  Write-Output ('WARNING: BI workbook normalization skipped: ' + $_.Exception.Message);" ^
    "} finally {" ^
    "  if ($workbook -ne $null) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) }" ^
    "  if ($excel -ne $null) {" ^
    "    $excel.Quit();" ^
    "    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)" ^
    "  }" ^
    "}" >> "%LOG_FILE%" 2>&1
)

:finish
REM Avaktivera venv om deactivate finns
if defined VIRTUAL_ENV if exist ".venv\Scripts\deactivate.bat" (
  call ".venv\Scripts\deactivate.bat" >> "%LOG_FILE%" 2>&1
)

set "STATUS=FAILED"
if "%ERR%"=="0" set "STATUS=SUCCESS"

>> "%LOG_FILE%" echo ============================================================
>> "%LOG_FILE%" echo End: %date% %time%
>> "%LOG_FILE%" echo Status: %STATUS%
>> "%LOG_FILE%" echo Result code: %ERR%
>> "%LOG_FILE%" echo Log: %LOG_FILE%
>> "%LOG_FILE%" echo ============================================================

start "" notepad "%LOG_FILE%"

exit /b %ERR%
