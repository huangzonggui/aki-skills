@echo off
REM aki-content-pipeline-pro setup for Windows
echo === Aki Content Pipeline Pro Setup ===

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Python not found. Install from https://python.org
    exit /b 1
)
echo [OK] Python found

pip install Pillow >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Pillow installed
) else (
    echo [WARN] Could not install Pillow. pip install Pillow manually.
)

if not exist "%USERPROFILE%\.config\ai\keys.env" (
    echo [WARN] No config found. Copy config\keys.env.example to %USERPROFILE%\.config\ai\keys.env
) else (
    echo [OK] Config found
)

echo Setup complete. Run: python scripts\check_env.py
