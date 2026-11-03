@echo off
setlocal enabledelayedexpansion

title Marvel Payout & Tax Extractor

echo ======================================================
echo          Marvel Payout & Tax Extractor Launcher
echo ======================================================

set "PYTHON_EXE="

:: 1. Check if python is directly accessible and working
python -c "import sys" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
)

:: 2. Check py launcher
if not defined PYTHON_EXE (
    py -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=py"
    )
)

:: 3. Check common Python installation paths on Windows
if not defined PYTHON_EXE (
    if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    ) else if exist "%ProgramFiles%\Python313\python.exe" (
        set "PYTHON_EXE=%ProgramFiles%\Python313\python.exe"
    ) else if exist "%ProgramFiles%\Python312\python.exe" (
        set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
    ) else if exist "C:\Python313\python.exe" (
        set "PYTHON_EXE=C:\Python313\python.exe"
    ) else if exist "C:\Python312\python.exe" (
        set "PYTHON_EXE=C:\Python312\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python was not found on this system.
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON_EXE%
echo.
echo ======================================================
echo Starting Marvel Payout Extractor...
echo ======================================================
"%PYTHON_EXE%" marvel_payout_extractor.py

pause
