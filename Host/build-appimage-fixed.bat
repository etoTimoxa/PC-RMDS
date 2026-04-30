@echo off
echo ==========================================
echo   Remote Access Agent - AppImage Builder
echo   (Полноценная версия)
echo ==========================================
echo.

where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Docker not installed!
    pause
    exit /b 1
)

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo 🔨 Building Docker image...
docker build -f Dockerfile.appimage-fixed -t pc-rmds-builder .
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo 📦 Creating output...
if not exist "output-qt5" mkdir output-qt5

docker run --rm -v "%CD%\output-qt5:/output" pc-rmds-builder

echo.
echo ==========================================
echo   ✅ Build complete!
echo ==========================================
echo.
echo 📁 Output: %CD%\output-qt5
echo.
echo 📋 На целевой машине (Linux):
echo    1. Скопируйте RemoteAccessAgent.AppImage
echo    2. Сделайте исполняемым: chmod +x RemoteAccessAgent.AppImage
echo    3. Запустите: ./RemoteAccessAgent.AppImage
echo.

pause