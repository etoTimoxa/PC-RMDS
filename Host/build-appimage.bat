@echo off
REM Build script for creating AppImage using Docker (Windows version)
REM This script builds a Linux AppImage of the Remote Access Agent

echo ==========================================
echo   Remote Access Agent - AppImage Builder
echo ==========================================
echo.

REM Check if Docker is installed
where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Docker is not installed. Please install Docker Desktop first.
    exit /b 1
)

echo ✅ Docker is installed
echo.

REM Get the directory of this script
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo 📁 Project directory: %SCRIPT_DIR%
echo.

REM Check if app_icon.png exists
if not exist "app_icon.png" (
    echo ❌ app_icon.png not found! Please provide an icon file.
    echo    The icon should be at least 256x256 pixels.
    exit /b 1
)

echo ✅ Icon file found: app_icon.png
echo.

REM Build the Docker image
echo 🔨 Building Docker image...
docker build -t pc-rmds-appimage-builder .
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Docker build failed!
    exit /b 1
)

echo ✅ Docker image built successfully
echo.

REM Create output directory
if not exist "output" mkdir output

REM Run the container to build AppImage
echo 📦 Building AppImage inside container...
docker run --rm ^
    -v "%CD%\output:/output" ^
    pc-rmds-appimage-builder
if %ERRORLEVEL% NEQ 0 (
    echo ❌ AppImage build failed!
    echo    Check the Docker output for details.
    exit /b 1
)

echo.
echo ==========================================
echo   ✅ AppImage build completed!
echo ==========================================
echo.
echo 📁 Output directory: %CD%\output
echo.
echo 📋 Next steps:
echo    1. Copy the AppImage to a Linux system
echo    2. Make it executable: chmod +x RemoteAccessAgent-*.AppImage
echo    3. Run: ./RemoteAccessAgent-*.AppImage
echo.
echo ⚠️  Note: AppImage is a Linux format and cannot be run on Windows.
echo    You need to transfer the file to a Linux machine to use it.
echo.

pause