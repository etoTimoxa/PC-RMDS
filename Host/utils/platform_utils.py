"""
Утилиты для кроссплатформенной работы
"""
import sys
import os
from pathlib import Path


def get_data_dir() -> Path:
    """
    Возвращает директорию для хранения данных приложения.
    
    Windows: %APPDATA%/RemoteAccessAgent/
    Linux: ~/.local/share/RemoteAccessAgent/
    macOS: ~/Library/Application Support/RemoteAccessAgent/
    """
    if sys.platform == 'win32':
        # Windows: %APPDATA%/RemoteAccessAgent/
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            return Path(appdata) / 'RemoteAccessAgent'
        # Fallback
        return Path.home() / 'AppData' / 'Roaming' / 'RemoteAccessAgent'
    
    elif sys.platform == 'darwin':
        # macOS: ~/Library/Application Support/RemoteAccessAgent/
        return Path.home() / 'Library' / 'Application Support' / 'RemoteAccessAgent'
    
    else:
        # Linux: ~/.local/share/RemoteAccessAgent/
        xdg_data = os.environ.get('XDG_DATA_HOME', '')
        if xdg_data:
            return Path(xdg_data) / 'RemoteAccessAgent'
        return Path.home() / '.local' / 'share' / 'RemoteAccessAgent'


def get_config_dir() -> Path:
    """
    Возвращает директорию для хранения конфигурации.
    
    Windows: %APPDATA%/RemoteAccessAgent/config/
    Linux: ~/.config/RemoteAccessAgent/
    """
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            return Path(appdata) / 'RemoteAccessAgent' / 'config'
        return Path.home() / 'AppData' / 'Roaming' / 'RemoteAccessAgent' / 'config'
    
    else:
        # Linux: ~/.config/RemoteAccessAgent/
        xdg_config = os.environ.get('XDG_CONFIG_HOME', '')
        if xdg_config:
            return Path(xdg_config) / 'RemoteAccessAgent'
        return Path.home() / '.config' / 'RemoteAccessAgent'


def get_cache_dir() -> Path:
    """
    Возвращает директорию для кэша.
    
    Windows: %LOCALAPPDATA%/RemoteAccessAgent/cache/
    Linux: ~/.cache/RemoteAccessAgent/
    """
    if sys.platform == 'win32':
        localappdata = os.environ.get('LOCALAPPDATA', '')
        if localappdata:
            return Path(localappdata) / 'RemoteAccessAgent' / 'cache'
        return Path.home() / 'AppData' / 'Local' / 'RemoteAccessAgent' / 'cache'
    
    else:
        # Linux: ~/.cache/RemoteAccessAgent/
        xdg_cache = os.environ.get('XDG_CACHE_HOME', '')
        if xdg_cache:
            return Path(xdg_cache) / 'RemoteAccessAgent'
        return Path.home() / '.cache' / 'RemoteAccessAgent'


def ensure_dirs():
    """Создает все необходимые директории"""
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_cache_dir().mkdir(parents=True, exist_ok=True)


def is_windows() -> bool:
    """Проверяет, запущено ли приложение на Windows"""
    return sys.platform == 'win32'


def is_linux() -> bool:
    """Проверяет, запущено ли приложение на Linux"""
    return sys.platform == 'linux'


def is_macos() -> bool:
    """Проверяет, запущено ли приложение на macOS"""
    return sys.platform == 'darwin'


def get_platform_name() -> str:
    """Возвращает название текущей платформы"""
    if is_windows():
        return 'Windows'
    elif is_linux():
        return 'Linux'
    elif is_macos():
        return 'macOS'
    return sys.platform