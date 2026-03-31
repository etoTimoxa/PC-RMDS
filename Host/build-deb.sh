#!/bin/bash
# Скрипт для сборки .deb пакета Remote Access Agent

VERSION="1.0.0"
PACKAGE_NAME="remote-access-agent"

echo "=== Начало сборки .deb пакета ==="

# Проверка на Linux
if [ "$(uname)" != "Linux" ]; then
    echo "Ошибка: Этот скрипт предназначен только для Linux!"
    echo "Для сборки .deb пакета необходимо запустить его на Linux системе."
    exit 1
fi

# Очистка старых сборок
echo "Очистка старых сборок..."
rm -rf dist build $PACKAGE_NAME $PACKAGE_NAME.deb 2>/dev/null

# Проверка PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller не найден. Устанавливаю..."
    pip install pyinstaller
fi

# Сборка через PyInstaller
echo "Сборка приложения через PyInstaller..."
pyinstaller --onefile --windowed --name="$PACKAGE_NAME" --icon=app_icon.ico main.py

if [ $? -ne 0 ]; then
    echo "Ошибка сборки PyInstaller!"
    exit 1
fi

# Создание структуры .deb пакета
echo "Создание структуры .deb пакета..."
mkdir -p $PACKAGE_NAME/DEBIAN
mkdir -p $PACKAGE_NAME/usr/bin
mkdir -p $PACKAGE_NAME/usr/share/applications

# Копирование файлов
echo "Копирование файлов..."
cp dist/$PACKAGE_NAME $PACKAGE_NAME/usr/bin/

# Control файл
echo "Создание control файла..."
cat > $PACKAGE_NAME/DEBIAN/control << EOF
Package: $PACKAGE_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: amd64
Depends: libc6, libqt6core6, libqt6gui6, libqt6widgets6
Maintainer: PC-RMDS Team <support@pc-rmds.com>
Description: Remote Access Agent for PC monitoring and remote control
 Remote Access Agent provides real-time monitoring, remote control,
 and cloud backup capabilities for Windows and Linux systems.
EOF

# postinst скрипт
cat > $PACKAGE_NAME/DEBIAN/postinst << 'EOF'
#!/bin/bash
chmod +x /usr/bin/remote-access-agent
echo "Remote Access Agent успешно установлен!"
EOF
chmod 755 $PACKAGE_NAME/DEBIAN/postinst

# prerm скрипт (удаление)
cat > $PACKAGE_NAME/DEBIAN/prerm << 'EOF'
#!/bin/bash
echo "Удаление Remote Access Agent..."
EOF
chmod 755 $PACKAGE_NAME/DEBIAN/prerm

# .desktop файл
echo "Создание .desktop файла..."
cat > $PACKAGE_NAME/usr/share/applications/remote-access-agent.desktop << EOF
[Desktop Entry]
Version=$VERSION
Type=Application
Name=Remote Access Agent
Comment=Remote monitoring and control
Exec=/usr/bin/remote-access-agent
Icon=/usr/bin/app_icon.ico
Terminal=false
Categories=Utility;RemoteAccess;Monitor;
Keywords=remote;monitor;control;agent;
EOF

# Сборка .deb пакета
echo "Сборка .deb пакета..."
dpkg-deb --build $PACKAGE_NAME

if [ $? -eq 0 ]; then
    echo "=== Сборка завершена успешно! ==="
    echo "Пакет: $PACKAGE_NAME.deb"
    echo "Размер: $(du -h $PACKAGE_NAME.deb | cut -f1)"
    echo ""
    echo "Для установки выполните:"
    echo "  sudo dpkg -i $PACKAGE_NAME.deb"
    echo ""
    echo "Для удаления выполните:"
    echo "  sudo apt remove $PACKAGE_NAME"
else
    echo "Ошибка сборки .deb пакета!"
    exit 1
fi