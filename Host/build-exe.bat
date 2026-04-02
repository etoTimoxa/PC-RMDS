@echo off
chcp 65001 >nul
REM Скрипт для сборки EXE файла Remote Access Agent для Windows

set VERSION=1.0.0
set APP_NAME=RemoteAccessAgent

echo === Начало сборки EXE файла ===

REM Очистка старых сборок
echo Очистка старых сборок...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del /q "*.spec"

REM Проверка PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller не найден. Устанавливаю...
    pip install pyinstaller
)

REM Сборка через PyInstaller (исключаем PyQt5 чтобы избежать конфликта)
echo Сборка приложения через PyInstaller...
C:\Users\Тимофей\AppData\Local\Programs\Python\Python312\Scripts\pyinstaller --onefile --windowed --name="%APP_NAME%" --icon=app_icon.ico --add-data "app_icon.ico;." --exclude-module PyQt5 --collect-all PyQt6 main.py

if errorlevel 1 (
    echo Ошибка сборки PyInstaller!
    pause
    exit /b 1
)

echo === Сборка завершена успешно! ===
echo EXE файл: dist\%APP_NAME%.exe
echo.
echo Для запуска выполните:
echo   dist\%APP_NAME%.exe
echo.

pause
