@echo off
setlocal enabledelayedexpansion

title CRS Automation

echo ======================================================
echo           CRS Automation Launcher
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
    echo Please make sure Python is installed and check "Add Python to PATH".
    echo ======================================================
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON_EXE%
echo.
echo Installing / verifying required libraries...
"%PYTHON_EXE%" -m pip install pandas requests openpyxl selenium webdriver-manager
if %errorlevel% neq 0 (
    echo [WARNING] Some dependencies might have failed to install. Proceeding...
)

echo.
echo ======================================================
echo Starting Automation Script...
echo ======================================================
"%PYTHON_EXE%" crs_bid_extractor.py

pause
