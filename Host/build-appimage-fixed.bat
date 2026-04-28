@echo off
REM Build script for creating AppImage using FIXED Dockerfile for old processors
REM Этот скрипт собирает AppImage с поддержкой Qt5 и старых процессоров
REM (без требований SSE4.1/4.2)

echo ==========================================
echo   Remote Access Agent - AppImage Builder
echo   ✅ Версия для старых процессоров (Qt5)
echo   ✅ Без требований SSE4.1/4.2
echo ==========================================
echo.

REM Check if Docker is installed
where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Docker is not installed. Please install Docker Desktop first.
    pause
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
    echo ⚠️  app_icon.png not found! Creating a placeholder...
    echo. 
    echo Create a simple placeholder or provide your own icon.
    echo The icon should be at least 256x256 pixels.
    echo.
)

echo.

REM Build the Docker image using FIXED Dockerfile with Qt5
echo 🔨 Building Docker image (Qt5, старые процессоры)...
docker build -f Dockerfile.appimage-fixed -t pc-rmds-appimage-builder-qt5 .
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Docker build failed!
    pause
    exit /b 1
)

echo ✅ Docker image built successfully
echo.

REM Create output directory
if not exist "output-qt5" mkdir output-qt5

REM Run the container to build AppImage
echo 📦 Building AppImage with Qt5 inside container...
echo ⏱️  This may take 5-10 minutes...
echo.
docker run --rm ^
    -v "%CD%\output-qt5:/output" ^
    pc-rmds-appimage-builder-qt5
if %ERRORLEVEL% NEQ 0 (
    echo ❌ AppImage build failed!
    echo    Check the Docker output for details.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   ✅ AppImage build completed!
echo ==========================================
echo.
echo 📁 Output directory: %CD%\output-qt5
echo.
echo ✅ Поддержка Qt5 (без SSE4.1/4.2 инструкций)
echo ✅ Работает на старых процессорах:
echo    - Intel Core 2 Duo/Quad (и старше)
echo    - AMD Phenom II/Athlon II
echo    - Любые процессоры 2008 года и старше
echo.
echo 📋 Next steps:
echo    1. Copy the AppImage to old laptop/PC
echo    2. Make it executable: chmod +x RemoteAccessAgent-*.AppImage
echo    3. Run: ./RemoteAccessAgent-*.AppImage
echo.
echo ⚠️  Note: AppImage is a Linux format and cannot be run on Windows.
echo.

pause