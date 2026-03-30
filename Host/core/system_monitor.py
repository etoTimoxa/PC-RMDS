import ctypes
import psutil
from ctypes import wintypes
import win32process
import win32api
import win32con
from datetime import datetime, timedelta
import time


class SystemActivityMonitor:
    
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    
    # Системные процессы, которые считаются активностью
    SYSTEM_PROCESSES = [
        'svchost.exe',      # Службы Windows
        'services.exe',     # Диспетчер служб
        'lsass.exe',        # Local Security Authority
        'winlogon.exe',     # Вход в систему
        'csrss.exe',        # Client Server Runtime
        'System',           # Система
        'Registry',         # Реестр
        'smss.exe',         # Session Manager
        'wininit.exe',      # Windows Init
        'spoolsv.exe',      # Принтеры
        'SearchIndexer.exe', # Поиск Windows
        'WmiPrvSE.exe',     # WMI
        'dwm.exe',          # Desktop Window Manager
        'explorer.exe',     # Проводник
        'Taskmgr.exe',      # Диспетчер задач
        'msedge.exe',       # Edge
        'chrome.exe',       # Chrome
        'firefox.exe',      # Firefox
        'Code.exe',         # VS Code
        'python.exe',       # Python
        'powershell.exe',   # PowerShell
        'cmd.exe',          # Command Prompt
    ]
    
    # События Windows, которые считаются активностью
    SYSTEM_EVENTS = [
        'Application',      # Приложения
        'System',           # Системные события
        'Security',         # Безопасность
        'Windows PowerShell', # PowerShell
        'Microsoft-Windows-*', # Windows компоненты
    ]
    
    _last_cpu_check = None
    _last_network_check = None
    _last_disk_check = None
    _last_memory_check = None
    
    @staticmethod
    def get_last_input_time() -> float:
        """Время с последнего ввода мыши/клавиатуры"""
        try:
            lastInputInfo = SystemActivityMonitor.LASTINPUTINFO()
            lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo))
            tickCount = ctypes.windll.kernel32.GetTickCount()
            return (tickCount - lastInputInfo.dwTime) / 1000.0
        except:
            return 0
    
    @staticmethod
    def get_cpu_usage() -> float:
        """Загрузка CPU"""
        try:
            return psutil.cpu_percent(interval=1)
        except:
            return 0
    
    @staticmethod
    def get_system_processes_activity() -> bool:
        """Проверяет наличие системных процессов"""
        try:
            found_processes = []  # Список для хранения найденных системных процессов
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info['name'].lower() if proc_info['name'] else ''
                    
                    # Проверяем, является ли процесс системным
                    is_system = any(sys_proc.lower() in proc_name for sys_proc in SystemActivityMonitor.SYSTEM_PROCESSES)
                    
                    if is_system:
                        found_processes.append(f"{proc_info['name']} (PID: {proc_info['pid']})")
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                
        except Exception as e:
            print(f"❌ Ошибка проверки системных процессов: {e}")
            return False
    
    @staticmethod
    def get_network_activity() -> bool:
        """Проверяет сетевую активность"""
        try:
            network_threshold = 1024 * 10  # 10 KB/s порог
            
            net_io = psutil.net_io_counters()
            current_time = time.time()
            
            if SystemActivityMonitor._last_network_check is not None:
                bytes_sent = net_io.bytes_sent - SystemActivityMonitor._last_network_check.get('bytes_sent', 0)
                bytes_recv = net_io.bytes_recv - SystemActivityMonitor._last_network_check.get('bytes_recv', 0)
                time_diff = current_time - SystemActivityMonitor._last_network_check.get('time', current_time)
                
                if time_diff > 0:
                    sent_rate = bytes_sent / time_diff
                    recv_rate = bytes_recv / time_diff
                    
                    if sent_rate > network_threshold or recv_rate > network_threshold:
                        return True
            
            SystemActivityMonitor._last_network_check = {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'time': current_time
            }
            
            return False
        except Exception as e:
            print(f"Ошибка проверки сети: {e}")
            return False
    
    @staticmethod
    def get_disk_activity() -> bool:
        """Проверяет дисковую активность"""
        try:
            disk_threshold = 1024 * 100  # 100 KB/s порог
            
            disk_io = psutil.disk_io_counters()
            current_time = time.time()
            
            if SystemActivityMonitor._last_disk_check is not None:
                read_bytes = disk_io.read_bytes - SystemActivityMonitor._last_disk_check.get('read_bytes', 0)
                write_bytes = disk_io.write_bytes - SystemActivityMonitor._last_disk_check.get('write_bytes', 0)
                time_diff = current_time - SystemActivityMonitor._last_disk_check.get('time', current_time)
                
                if time_diff > 0:
                    read_rate = read_bytes / time_diff
                    write_rate = write_bytes / time_diff
                    
                    if read_rate > disk_threshold or write_rate > disk_threshold:
                        return True
            
            SystemActivityMonitor._last_disk_check = {
                'read_bytes': disk_io.read_bytes,
                'write_bytes': disk_io.write_bytes,
                'time': current_time
            }
            
            return False
        except Exception as e:
            print(f"Ошибка проверки диска: {e}")
            return False
    
    @staticmethod
    def get_memory_activity() -> bool:
        """Проверяет изменения в использовании памяти"""
        try:
            memory = psutil.virtual_memory()
            current_time = time.time()
            
            if SystemActivityMonitor._last_memory_check is not None:
                memory_change = abs(memory.used - SystemActivityMonitor._last_memory_check.get('memory_used', 0))
                time_diff = current_time - SystemActivityMonitor._last_memory_check.get('time', current_time)
                
                if time_diff > 0:
                    change_rate = memory_change / time_diff
                    if change_rate > 1024 * 1024 * 10:  # 10 MB/s порог
                        return True
            
            SystemActivityMonitor._last_memory_check = {
                'memory_used': memory.used,
                'time': current_time
            }
            
            return False
        except Exception as e:
            print(f"Ошибка проверки памяти: {e}")
            return False
    
    @staticmethod
    def get_system_uptime() -> float:
        """Время работы системы в секундах"""
        try:
            return time.time() - psutil.boot_time()
        except:
            return 0
    
    @staticmethod
    def is_system_active() -> bool:
        """Проверяет активность системы (работа Windows, процессы, сеть, диск)"""
        
        # 1. Проверяем активность системных процессов
        if SystemActivityMonitor.get_system_processes_activity():
            return True
        
        return False
    
    @staticmethod
    def get_activity_description() -> str:
        """Возвращает описание текущей активности"""
        activities = []
        
        # Проверяем различные виды активности
        if SystemActivityMonitor.get_system_processes_activity():
            activities.append("Активность системных процессов")
        
        if SystemActivityMonitor.get_network_activity():
            activities.append("Сетевая активность")
        
        if SystemActivityMonitor.get_disk_activity():
            activities.append("Дисковая активность")
        
        if SystemActivityMonitor.get_memory_activity():
            activities.append("Активность памяти")
        
        cpu_usage = SystemActivityMonitor.get_cpu_usage()
        if cpu_usage > 5:
            activities.append(f"Загрузка CPU: {cpu_usage:.1f}%")
        
        last_input = SystemActivityMonitor.get_last_input_time()
        if last_input < 300:
            activities.append(f"Пользователь активен: {int(last_input)} сек назад")
        
        return ", ".join(activities) if activities else "Система в режиме ожидания"