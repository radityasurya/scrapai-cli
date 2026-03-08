@echo off
REM Generate requirements.lock for production deployments (Windows)
REM
REM This script creates a lockfile with exact versions of all dependencies
REM for use in production deployments where reproducibility is critical.
REM
REM Usage:
REM   scripts\generate-lockfile.bat
REM
REM Output:
REM   requirements.lock - Exact versions of all installed packages
REM

echo 🔒 Generating requirements.lock for production deployment...
echo.

REM Check if we're in a virtual environment
if "%VIRTUAL_ENV%"=="" (
    echo ⚠️  WARNING: Not running in a virtual environment
    echo    Consider activating venv first: .venv\Scripts\activate
    echo.
)

REM Install requirements to ensure all dependencies are present
echo 📦 Installing dependencies from requirements.txt...
pip install -q -r requirements.txt

REM Generate lockfile
echo 🔒 Generating lockfile...
pip freeze > requirements.lock

REM Validate lockfile
if exist requirements.lock (
    for /f %%A in ("requirements.lock") do set PACKAGE_COUNT=%%~zA
    if %PACKAGE_COUNT% gtr 0 (
        echo ✅ Lockfile generated successfully
        echo    File: requirements.lock
        echo.
        echo 📋 Top 10 packages:
        more +0 requirements.lock | findstr /n "^" | findstr "^[1-9]:" | more
        echo.
        echo 💡 Usage in production:
        echo    pip install -r requirements.lock
        echo.
        echo ⚠️  Note: Do not commit requirements.lock to git
        echo    Add to .gitignore if not already present
    ) else (
        echo ❌ Error: Lockfile is empty
        exit /b 1
    )
) else (
    echo ❌ Error: Failed to create lockfile
    exit /b 1
)
