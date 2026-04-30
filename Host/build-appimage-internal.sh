#!/bin/bash
# Полноценная сборка AppImage

echo "=========================================="
echo "  Сборка полноценного AppImage"
echo "=========================================="

APP_NAME="RemoteAccessAgent"
APP_DIR="AppDir"
ARCH=$(uname -m)

rm -rf dist build $APP_DIR *.AppImage *.tar.gz 2>/dev/null || true

# Сборка через PyInstaller
pyinstaller --onefile --windowed \
    --name="$APP_NAME" \
    --icon=app_icon.png \
    --exclude-module=win32process \
    --exclude-module=win32api \
    --exclude-module=win32con \
    --exclude-module=win32evtlog \
    --exclude-module=pythoncom \
    --exclude-module=pywintypes \
    --hidden-import=qtpy \
    --hidden-import=qtpy.QtWidgets \
    --hidden-import=qtpy.QtCore \
    --hidden-import=qtpy.QtGui \
    --add-data="app_icon.png:." \
    main.py

# Создание структуры AppDir
mkdir -p $APP_DIR/usr/bin
mkdir -p $APP_DIR/usr/share/applications
mkdir -p $APP_DIR/usr/share/icons/hicolor/256x256/apps

cp dist/$APP_NAME $APP_DIR/usr/bin/
chmod +x $APP_DIR/usr/bin/$APP_NAME

if [ -f "app_icon.png" ]; then
    cp app_icon.png $APP_DIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png
    cp app_icon.png $APP_DIR/$APP_NAME.png
fi

cat > $APP_DIR/$APP_NAME.desktop << EOF
[Desktop Entry]
Type=Application
Name=Remote Access Agent
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Utility;
EOF

cat > $APP_DIR/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/RemoteAccessAgent" "$@"
EOF
chmod +x $APP_DIR/AppRun

# Скачиваем appimagetool
echo "📥 Скачиваем appimagetool..."
wget -q -O appimagetool "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
chmod +x appimagetool

# Создаем AppImage
echo "🔨 Создаем AppImage..."
./appimagetool --no-appstream $APP_DIR

if [ -f "${APP_NAME}-${ARCH}.AppImage" ]; then
    mv "${APP_NAME}-${ARCH}.AppImage" RemoteAccessAgent.AppImage
    chmod +x RemoteAccessAgent.AppImage
    echo "✅ AppImage успешно создан: RemoteAccessAgent.AppImage"
    ls -lh *.AppImage
    
    # Копируем в output
    if [ -d "/output" ]; then
        cp *.AppImage /output/
    fi
else
    echo "❌ Ошибка при создании AppImage"
    # Создаем резервный архив на случай неудачи
    tar -czf RemoteAccessAgent-qt5-AppDir.tar.gz $APP_DIR
    if [ -d "/output" ]; then
        cp *.tar.gz /output/
    fi
    exit 1
fi

rm -f appimagetool
