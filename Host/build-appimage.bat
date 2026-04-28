@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Скрипт для сборки Portable EXE Remote Access Agent (аналог AppImage на Windows)

set VERSION=1.0.0
set APP_NAME=RemoteAccessAgent
set DIST_DIR=dist

echo === Начало сборки Portable EXE ===

:: Проверка на Windows
if not "%OS%"=="Windows_NT" (
    echo Ошибка: Этот скрипт предназначен только для Windows!
    exit /b 1
)

:: Очистка старых сборок
echo Очистка старых сборок...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.exe del /q *.exe 2>nul

:: Проверка Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Ошибка: Python не найден в PATH!
    echo Установите Python с https://www.python.org/downloads/
    exit /b 1
)

:: Проверка PyInstaller
echo Проверка PyInstaller...
pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo PyInstaller не найден. Устанавливаю...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo Ошибка установки PyInstaller!
        exit /b 1
    )
)

:: Сборка через PyInstaller
echo Сборка приложения через PyInstaller...
if exist app_icon.png (
    pyinstaller --onefile --windowed --name="%APP_NAME%" --icon=app_icon.png main.py
) else (
    pyinstaller --onefile --windowed --name="%APP_NAME%" main.py
)

if %errorlevel% neq 0 (
    echo Ошибка сборки PyInstaller!
    exit /b 1
)

:: Копирование готового EXE
echo Копирование готового EXE...
copy "%DIST_DIR%\%APP_NAME%.exe" .\ >nul

if %errorlevel% neq 0 (
    echo Ошибка копирования EXE!
    exit /b 1
)

:: Создание ZIP-архива с дополнительными файлами (опционально)
echo Создание портативной упаковки...
if exist "%APP_NAME%_portable" rmdir /s /q "%APP_NAME%_portable"
mkdir "%APP_NAME%_portable" 2>nul
copy "%APP_NAME%.exe" "%APP_NAME%_portable\" >nul

:: Копирование readme если есть
if exist README.md copy README.md "%APP_NAME%_portable\" >nul

:: Создание bat-файла для запуска в портативной папке
echo @echo off > "%APP_NAME%_portable\Запустить_агента.bat"
echo echo === Remote Access Agent === >> "%APP_NAME%_portable\Запустить_агента.bat"
echo echo. >> "%APP_NAME%_portable\Запустить_агента.bat"
echo echo Запуск агента... >> "%APP_NAME%_portable\Запустить_агента.bat"
echo %APP_NAME%.exe >> "%APP_NAME%_portable\Запустить_агента.bat"
echo if %%errorlevel%% neq 0 ( >> "%APP_NAME%_portable\Запустить_агента.bat"
echo     echo Ошибка запуска! >> "%APP_NAME%_portable\Запустить_агента.bat"
echo     pause >> "%APP_NAME%_portable\Запустить_агента.bat"
echo ) >> "%APP_NAME%_portable\Запустить_агента.bat"

:: Создание ZIP-архива
echo Архивирование портативной версии...
if exist "%APP_NAME%_v%VERSION%_portable.zip" del "%APP_NAME%_v%VERSION%_portable.zip"

:: Используем PowerShell для создания ZIP (есть во всех современных Windows)
powershell -command "Compress-Archive -Path '%APP_NAME%_portable\*' -DestinationPath '%APP_NAME%_v%VERSION%_portable.zip' -Force"

if %errorlevel% equ 0 (
    echo.
    echo === Сборка завершена успешно! ===
    echo Готовый EXE: %APP_NAME%.exe
    echo Портативная упаковка: %APP_NAME%_v%VERSION%_portable.zip
    echo Размер: 
    dir %APP_NAME%.exe 2>nul | find "%APP_NAME%.exe"
    echo.
    echo Для запуска выполните:
    echo   %APP_NAME%.exe
    echo.
    echo Для портативного использования:
    echo   1. Распакуйте ZIP архив
    echo   2. Запустите Запустить_агента.bat
    echo.
) else (
    echo Ошибка создания ZIP архива!
    echo Но основной EXE файл создан: %APP_NAME%.exe
)

:: Очистка временных файлов сборки (опционально)
echo.
echo Очистка временных файлов сборки...
rmdir /s /q build 2>nul
rmdir /s /q __pycache__ 2>nul
del /q %APP_NAME%.spec 2>nul

echo Готово!
pause