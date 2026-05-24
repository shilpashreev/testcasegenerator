@echo off
title Test Case Generator

echo ============================================================
echo   Test Case Generator - Startup
echo ============================================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Install dependencies if needed
echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/2] Starting app...
echo.
echo Open your browser at: http://localhost:8501
echo Press Ctrl+C to stop.
echo.

python -m streamlit run app.py --server.port 8501 --server.headless false
pause
