#!/bin/bash
# Внутренний скрипт для сборки AppImage внутри Docker контейнера
# This script runs inside the Docker container to build the AppImage

set -e

echo "=========================================="
echo "  Remote Access Agent - AppImage Builder"
echo "  (Internal Docker Build)"
echo "=========================================="
echo ""

VERSION="1.0.0"
APP_NAME="RemoteAccessAgent"
APP_DIR="AppDir"

# Проверка на Linux
if [ "$(uname)" != "Linux" ]; then
    echo "Ошибка: Этот скрипт предназначен только для Linux!"
    exit 1
fi

# Очистка старых сборок
echo "🧹 Очистка старых сборок..."
rm -rf dist build $APP_DIR *.AppImage 2>/dev/null || true

# Проверка PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ PyInstaller не найден. Устанавливаю..."
    pip install pyinstaller
fi

# Сборка через PyInstaller
echo "🔨 Сборка приложения через PyInstaller..."
pyinstaller --onefile --windowed \
    --name="$APP_NAME" \
    --icon=app_icon.png \
    --exclude-module=win32process \
    --exclude-module=win32api \
    --exclude-module=win32con \
    --exclude-module=win32evtlog \
    --exclude-module=win32evtlogutil \
    --exclude-module=win32security \
    --exclude-module=pythoncom \
    --exclude-module=pywintypes \
    --hidden-import=PyQt6 \
    --hidden-import=PyQt6.QtCore \
    --hidden-import=PyQt6.QtGui \
    --hidden-import=PyQt6.QtWidgets \
    --hidden-import=PyQt6.QtNetwork \
    --collect-all PyQt6 \
    --hidden-import=psutil \
    --collect-all psutil \
    --hidden-import=pynput \
    --hidden-import=pynput.keyboard \
    --hidden-import=pynput.keyboard._xorg \
    --hidden-import=pynput.mouse \
    --hidden-import=pynput.mouse._xorg \
    --collect-all pynput \
    --hidden-import=sqlite3 \
    --hidden-import=platform \
    --hidden-import=socket \
    --hidden-import=subprocess \
    --hidden-import=threading \
    --hidden-import=json \
    --hidden-import=hashlib \
    --hidden-import=base64 \
    --hidden-import=uuid \
    --hidden-import=ctypes \
    --hidden-import=ctypes.util \
    --add-data="app_icon.png:." \
    main.py

if [ $? -ne 0 ]; then
    echo "❌ Ошибка сборки PyInstaller!"
    exit 1
fi

echo "✅ PyInstaller сборка завершена"
echo ""

# Создание структуры AppDir
echo "📁 Создание структуры AppDir..."
mkdir -p $APP_DIR/usr/bin
mkdir -p $APP_DIR/usr/share/applications
mkdir -p $APP_DIR/usr/share/icons/hicolor/256x256/apps
mkdir -p $APP_DIR/usr/share/icons/hicolor/128x128/apps
mkdir -p $APP_DIR/usr/share/icons/hicolor/64x64/apps
mkdir -p $APP_DIR/usr/share/icons/hicolor/48x48/apps
mkdir -p $APP_DIR/usr/share/icons/hicolor/32x32/apps
mkdir -p $APP_DIR/usr/share/icons/hicolor/16x16/apps

# Копирование бинарного файла
echo "📋 Копирование файлов..."
cp dist/$APP_NAME $APP_DIR/usr/bin/
chmod +x $APP_DIR/usr/bin/$APP_NAME

# Копирование иконок
echo "🎨 Копирование иконок..."
if [ -f "app_icon.png" ]; then
    cp app_icon.png $APP_DIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png
    
    # Создаем иконки разных размеров с помощью ImageMagick
    if command -v convert &> /dev/null; then
        for size in 128 64 48 32 16; do
            convert app_icon.png -resize ${size}x${size} \
                $APP_DIR/usr/share/icons/hicolor/${size}x${size}/apps/$APP_NAME.png
        done
    fi
    
    # Копируем большую иконку в корень AppDir
    cp app_icon.png $APP_DIR/$APP_NAME.png
    echo "✅ Иконки скопированы"
else
    echo "⚠️ Warning: app_icon.png not found"
fi

# Создание .desktop файла
echo "📄 Создание .desktop файла..."
cat > $APP_DIR/$APP_NAME.desktop << EOF
[Desktop Entry]
Type=Application
Name=Remote Access Agent
Comment=Remote monitoring and control agent
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Utility;Network;System;
Keywords=remote;monitor;control;agent;
EOF

# Копируем .desktop файл в нужное место
cp $APP_DIR/$APP_NAME.desktop $APP_DIR/usr/share/applications/$APP_NAME.desktop

# Создание AppRun
echo "🚀 Создание AppRun..."
cat > $APP_DIR/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${HERE}/usr/lib/x86_64-linux-gnu:${HERE}/usr/lib/qt6:${LD_LIBRARY_PATH}"
export QT_QPA_PLATFORM_PLUGIN_PATH="${HERE}/usr/lib/qt6/plugins"
export QT_PLUGIN_PATH="${HERE}/usr/lib/qt6/plugins"
export QML2_IMPORT_PATH="${HERE}/usr/lib/qt6/qml"
export QML_IMPORT_PATH="${HERE}/usr/lib/qt6/qml"
export FONTCONFIG_PATH="${HERE}/usr/etc/fonts"
exec "${HERE}/usr/bin/RemoteAccessAgent" "$@"
EOF
chmod +x $APP_DIR/AppRun

# Загрузка linuxdeploy
echo "⬇️ Загрузка linuxdeploy..."
if [ ! -f "linuxdeploy-x86_64.AppImage" ]; then
    wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
    chmod +x linuxdeploy-x86_64.AppImage
fi

# Сборка AppImage
echo "📦 Сборка AppImage..."
./linuxdeploy-x86_64.AppImage \
    --appimage-extract-and-run \
    --appdir $APP_DIR \
    --desktop-file=$APP_DIR/$APP_NAME.desktop \
    --icon-file=$APP_DIR/$APP_NAME.png \
    --output appimage

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "  ✅ Сборка завершена успешно!"
    echo "=========================================="
    echo ""
    ls -lh /app/*.AppImage || echo "Warning: AppImage not found"
    echo ""
else
    echo "❌ Ошибка сборки AppImage!"
    exit 1
fi