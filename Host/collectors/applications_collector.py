"""
Коллектор данных об установленных приложениях и отслеживание их установки/удаления
"""
import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime

if sys.platform == 'win32':
    import winreg

from utils.platform_utils import get_platform_name


class ApplicationsCollector:
    """
    Сборщик информации об установленных приложениях
    Отслеживает установку и удаление программ
    """
    
    _last_apps: Set[str] = set()
    _initialized = False
    
    @staticmethod
    def get_installed_applications() -> List[Dict]:
        """
        Возвращает список всех установленных приложений
        Работает на Windows и Linux
        """
        apps = []
        
        if sys.platform == 'win32':
            apps.extend(ApplicationsCollector._get_windows_applications())
        elif sys.platform == 'linux':
            apps.extend(ApplicationsCollector._get_linux_applications())
            
        return apps
    
    @staticmethod
    def _get_windows_applications() -> List[Dict]:
        """Получает список установленных приложений из реестра Windows"""
        apps = []
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        
        for hkey, path in reg_paths:
            try:
                key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        
                        name = winreg.QueryValueEx(subkey, "DisplayName")[0].strip() if ApplicationsCollector._reg_value_exists(subkey, "DisplayName") else None
                        if not name or name.startswith('Update for') or name.startswith('Security Update for') or 'KB' in name:
                            continue
                            
                        app = {
                            'name': name,
                            'version': winreg.QueryValueEx(subkey, "DisplayVersion")[0].strip() if ApplicationsCollector._reg_value_exists(subkey, "DisplayVersion") else None,
                            'publisher': winreg.QueryValueEx(subkey, "Publisher")[0].strip() if ApplicationsCollector._reg_value_exists(subkey, "Publisher") else None,
                            'install_date': winreg.QueryValueEx(subkey, "InstallDate")[0].strip() if ApplicationsCollector._reg_value_exists(subkey, "InstallDate") else None,
                            'install_location': winreg.QueryValueEx(subkey, "InstallLocation")[0].strip() if ApplicationsCollector._reg_value_exists(subkey, "InstallLocation") else None,
                            'uninstall_string': winreg.QueryValueEx(subkey, "UninstallString")[0].strip() if ApplicationsCollector._reg_value_exists(subkey, "UninstallString") else None,
                            'estimated_size': winreg.QueryValueEx(subkey, "EstimatedSize")[0] if ApplicationsCollector._reg_value_exists(subkey, "EstimatedSize") else None,
                            'system_app': False,
                            'platform': 'Windows'
                        }
                        
                        apps.append(app)
                        winreg.CloseKey(subkey)
                    except:
                        continue
                winreg.CloseKey(key)
            except:
                continue
                
        return apps
    
    @staticmethod
    def _reg_value_exists(key, value_name):
        """Проверяет существует ли значение в ключе реестра"""
        try:
            winreg.QueryValueEx(key, value_name)
            return True
        except:
            return False
    
    @staticmethod
    def _get_linux_applications() -> List[Dict]:
        """Получает список установленных приложений из .desktop файлов Linux"""
        apps = []
        desktop_paths = [
            Path('/usr/share/applications'),
            Path.home() / '.local/share/applications',
            '/var/lib/snapd/desktop/applications',
            '/usr/local/share/applications'
        ]
        
        processed = set()
        
        for base_path in desktop_paths:
            path = Path(base_path)
            if not path.exists():
                continue
                
            for desktop_file in path.glob('**/*.desktop'):
                try:
                    if not desktop_file.is_file():
                        continue
                        
                    app_id = desktop_file.stem
                    if app_id in processed:
                        continue
                        
                    content = desktop_file.read_text(encoding='utf-8', errors='ignore')
                    
                    app = {
                        'name': None,
                        'version': None,
                        'publisher': None,
                        'comment': None,
                        'exec': None,
                        'icon': None,
                        'categories': None,
                        'file_path': str(desktop_file),
                        'system_app': str(desktop_file).startswith('/usr/'),
                        'platform': 'Linux'
                    }
                    
                    for line in content.splitlines():
                        line = line.strip()
                        if '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip()
                            v = v.strip()
                            
                            if k == 'Name' and not app['name']:
                                app['name'] = v
                            elif k == 'Version':
                                app['version'] = v
                            elif k == 'Comment':
                                app['comment'] = v
                            elif k == 'Exec':
                                app['exec'] = v
                            elif k == 'Icon':
                                app['icon'] = v
                            elif k == 'Categories':
                                app['categories'] = v
                    
                    if app['name'] and not app['name'].startswith('org.') and not app_id.startswith('mimeinfo'):
                        processed.add(app_id)
                        apps.append(app)
                        
                except:
                    continue
                    
        return apps
    
    @classmethod
    def detect_changes(cls) -> Dict[str, List[Dict]]:
        """
        Обнаруживает приложения которые были установлены или удалены с прошлого вызова
        Возвращает словарь с ключами 'installed' и 'removed'
        """
        current_apps = cls.get_installed_applications()
        current_names = {app['name'] for app in current_apps if app['name']}
        
        result = {
            'installed': [],
            'removed': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not cls._initialized:
            cls._last_apps = current_names
            cls._initialized = True
            return result
            
        # Найти новые приложения
        installed_names = current_names - cls._last_apps
        result['installed'] = [app for app in current_apps if app['name'] in installed_names]
        
        # Найти удаленные приложения
        removed_names = cls._last_apps - current_names
        result['removed'] = [{'name': name} for name in removed_names]
        
        cls._last_apps = current_names
        
        return result
    
    @staticmethod
    def get_applications_count() -> int:
        """Возвращает количество установленных приложений"""
        return len(ApplicationsCollector.get_installed_applications())
    
    @staticmethod
    def get_running_processes() -> List[Dict]:
        """
        Возвращает список запущенных процессов (активных приложений)
        Фильтрует системные процессы и оставляет только пользовательские приложения
        """
        import psutil
        
        processes = []
        seen = set()
        
        ignored_names = {
            'system', 'svchost', 'services', 'lsass', 'wininit', 'winlogon',
            'csrss', 'smss', 'dwm', 'explorer', 'taskhostw', 'runtimebroker',
            'applicationframehost', 'sihost', 'fontdrvhost', 'wudfhost',
            'systemsettings', 'searchapp', 'searchui', 'startmenuexperiencehost',
            'systemd', 'kthreadd', 'kworker', 'rcu_sched', 'xorg', 'pulseaudio',
            'dbus-daemon', 'networkmanager', 'polkitd', 'gdm-x-session', 'gnome-shell',
            'kwin_x11', 'plasmashell', 'python', 'python3', 'cmd', 'powershell',
            'conhost', 'java', 'node', 'npm'
        }
        
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'create_time', 'username']):
            try:
                proc_info = proc.info
                
                if not proc_info['name']:
                    continue
                    
                name_lower = proc_info['name'].lower().replace('.exe', '').replace('.bin', '')
                if name_lower in ignored_names:
                    continue
                
                if proc_info['name'] in seen:
                    continue
                seen.add(proc_info['name'])
                
                process = {
                    'pid': proc_info['pid'],
                    'name': proc_info['name'],
                    'executable': proc_info['exe'],
                    'cmdline': ' '.join(proc_info['cmdline']) if proc_info['cmdline'] else None,
                    'start_time': datetime.fromtimestamp(proc_info['create_time']).isoformat() if proc_info['create_time'] else None,
                    'username': proc_info['username'],
                    'is_system': False,
                    'platform': get_platform_name()
                }
                
                processes.append(process)
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        return processes
    
    @classmethod
    def detect_process_changes(cls) -> Dict[str, List[Dict]]:
        """
        Обнаруживает приложения которые были запущены или закрыты с прошлого вызова
        Возвращает словарь с ключами 'started' и 'closed'
        """
        if not hasattr(cls, '_last_processes'):
            cls._last_processes = set()
            
        current_processes = cls.get_running_processes()
        current_names = {p['name'] for p in current_processes}
        
        result = {
            'started': [],
            'closed': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not cls._last_processes:
            cls._last_processes = current_names
            return result
            
        # Найти новые запущенные приложения
        started_names = current_names - cls._last_processes
        result['started'] = [p for p in current_processes if p['name'] in started_names]
        
        # Найти закрытые приложения
        closed_names = cls._last_processes - current_names
        result['closed'] = [{'name': name} for name in closed_names]
        
        cls._last_processes = current_names
        
        return result
