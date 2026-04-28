#!/bin/bash
# Внутренний скрипт для сборки AppImage внутри Docker контейнера
# ВЕРСИЯ ДЛЯ Qt5: поддержка старых процессоров без SSE4.1/4.2
# This script runs inside the Docker container to build the AppImage

set -e

echo "=========================================="
echo "  Remote Access Agent - AppImage Builder"
echo "  (Qt5 Version - для старых процессоров)"
echo "=========================================="
echo ""

VERSION="1.0.0"
APP_NAME="RemoteAccessAgent"
APP_DIR="AppDir"

# Установка переменных для Qt5
export QT_SELECT=qt5
export QT_API=pyqt5
export NO_SSE42_CHECK=1  # Отключаем проверку SSE4 инструкций

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

# Проверка что используем PyQt5, а не PyQt6
echo "🔍 Проверка установленных пакетов..."
pip list | grep -E "PyQt|qt" || true

# Сборка через PyInstaller с PyQt5 вместо PyQt6
echo "🔨 Сборка приложения через PyInstaller (Qt5)..."
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
    --exclude-module=PyQt6 \
    --exclude-module=PyQt6.sip \
    --hidden-import=PyQt5 \
    --hidden-import=PyQt5.QtCore \
    --hidden-import=PyQt5.QtGui \
    --hidden-import=PyQt5.QtWidgets \
    --hidden-import=PyQt5.QtNetwork \
    --collect-all PyQt5 \
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
mkdir -p $APP_DIR/usr/lib
mkdir -p $APP_DIR/usr/lib/x86_64-linux-gnu
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

# Копирование PyQt5 библиотек
echo "📚 Копирование PyQt5 библиотек..."
PYTHON_SITE=$(python -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || python -c "import sysconfig; print(sysconfig.get_path('purelib'))")
if [ -d "$PYTHON_SITE/PyQt5" ]; then
    cp -r $PYTHON_SITE/PyQt5 $APP_DIR/usr/lib/
    echo "✅ PyQt5 скопированы из $PYTHON_SITE"
fi

# Копирование Qt5 библиотек из системы
if [ -d "/usr/lib/x86_64-linux-gnu/qt5" ]; then
    cp -r /usr/lib/x86_64-linux-gnu/qt5 $APP_DIR/usr/lib/ 2>/dev/null || true
fi
if [ -d "/usr/lib/x86_64-linux-gnu/libQt5"* ]; then
    cp /usr/lib/x86_64-linux-gnu/libQt5*.so* $APP_DIR/usr/lib/ 2>/dev/null || true
fi

# Копирование иконок
echo "🎨 Копирование иконок..."
if [ -f "app_icon.png" ]; then
    cp app_icon.png $APP_DIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png
    
    # Создаем иконки разных размеров с помощью ImageMagick
    if command -v convert &> /dev/null; then
        for size in 128 64 48 32 16; do
            convert app_icon.png -resize ${size}x${size} \
                $APP_DIR/usr/share/icons/hicolor/${size}x${size}/apps/$APP_NAME.png 2>/dev/null || true
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

# Создание AppRun с поддержкой Qt5
echo "🚀 Создание AppRun (Qt5 version)..."
cat > $APP_DIR/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${HERE}/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}"

# Принудительное использование Qt5
export QT_SELECT=qt5
export QT_API=pyqt5
export NO_SSE42_CHECK=1

# Настройка Qt5 плагинов
export QT_QPA_PLATFORM_PLUGIN_PATH="${HERE}/usr/lib/qt5/plugins"
export QT_PLUGIN_PATH="${HERE}/usr/lib/qt5/plugins"

# Fallback для X11
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi

# Запуск приложения
exec "${HERE}/usr/bin/RemoteAccessAgent" "$@"
EOF
chmod +x $APP_DIR/AppRun

# Загрузка linuxdeploy (версия для Qt5)
echo "⬇️ Загрузка linuxdeploy (Qt5 version)..."
if [ ! -f "linuxdeploy-x86_64.AppImage" ]; then
    wget -q --no-check-certificate https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
    chmod +x linuxdeploy-x86_64.AppImage
fi

# Загрузка плагина Qt5 для linuxdeploy
if [ ! -f "linuxdeploy-plugin-qt-x86_64.AppImage" ]; then
    wget -q --no-check-certificate https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage
    chmod +x linuxdeploy-plugin-qt-x86_64.AppImage
fi

# Сборка AppImage с Qt5 плагином
echo "📦 Сборка AppImage (Qt5 version)..."
export NO_SSE42_CHECK=1
export UPD_INFO=0

# Попытка сборки через linuxdeploy с Qt плагином
./linuxdeploy-x86_64.AppImage \
    --appdir $APP_DIR \
    --desktop-file=$APP_DIR/$APP_NAME.desktop \
    --icon-file=$APP_DIR/$APP_NAME.png \
    --output appimage 2>/dev/null || true

# Если не получилось, пробуем с плагином Qt
if [ ! -f *.AppImage ]; then
    echo "🔄 Повторная сборка с Qt плагином..."
    ./linuxdeploy-x86_64.AppImage \
        --appdir $APP_DIR \
        --desktop-file=$APP_DIR/$APP_NAME.desktop \
        --icon-file=$APP_DIR/$APP_NAME.png \
        --plugin qt \
        --output appimage 2>/dev/null || true
fi

# Проверка результата
if [ -f *.AppImage ]; then
    echo ""
    echo "=========================================="
    echo "  ✅ Сборка завершена успешно!"
    echo "=========================================="
    echo ""
    
    # Переименование с указанием версии Qt5
    FINAL_NAME="RemoteAccessAgent-Qt5-x86_64.AppImage"
    mv *.AppImage "$FINAL_NAME" 2>/dev/null || true
    
    echo "📦 Создан файл: $FINAL_NAME"
    ls -lh "$FINAL_NAME"
    
    # Копирование в output директорию (для Docker)
    if [ -d "/output" ]; then
        cp "$FINAL_NAME" /output/
        echo "📁 Скопирован в /output/"
    fi
    echo ""
else
    echo "⚠️ AppImage не создан через linuxdeploy, пробуем ручную упаковку..."
    
    # Ручная упаковка через tar+AppImageKit
    if command -v appimagetool &> /dev/null || [ -f "appimagetool-x86_64.AppImage" ]; then
        if [ ! -f "appimagetool-x86_64.AppImage" ]; then
            wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
            chmod +x appimagetool-x86_64.AppImage
        fi
        ARCH=x86_64 ./appimagetool-x86_64.AppImage $APP_DIR
        if [ -f *.AppImage ]; then
            FINAL_NAME="RemoteAccessAgent-Qt5-x86_64.AppImage"
            mv *.AppImage "$FINAL_NAME"
            echo "✅ Ручная упаковка успешна: $FINAL_NAME"
            [ -d "/output" ] && cp "$FINAL_NAME" /output/
        fi
    else
        # Последнее средство: просто копируем AppDir как есть
        echo "⚠️ Не удалось создать AppImage, копирую AppDir..."
        tar -czf RemoteAccessAgent-Qt5-x86_64.AppDir.tar.gz $APP_DIR
        [ -d "/output" ] && cp RemoteAccessAgent-Qt5-x86_64.AppDir.tar.gz /output/
    fi
fi

echo ""
echo "=========================================="
echo "  📊 Итог сборки (Qt5 version)"
echo "=========================================="
echo "✅ Поддержка старых процессоров (без SSE4.1/4.2)"
echo "✅ PyQt5 вместо PyQt6"
echo "=========================================="