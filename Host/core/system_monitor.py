import ctypes
import psutil
from ctypes import wintypes


class SystemActivityMonitor:
    
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    
    @staticmethod
    def get_last_input_time() -> float:
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
        try:
            return psutil.cpu_percent(interval=1)
        except:
            return 0
    
    @staticmethod
    def is_system_active() -> bool:
        last_input = SystemActivityMonitor.get_last_input_time()
        if last_input < 300:
            return True
        cpu_usage = SystemActivityMonitor.get_cpu_usage()
        if cpu_usage > 10:
            return True
        return False
    
    @staticmethod
    def get_activity_description() -> str:
        activities = []
        last_input = SystemActivityMonitor.get_last_input_time()
        if last_input < 300:
            activities.append(f"Ввод: {int(last_input)} сек назад")
        cpu_usage = SystemActivityMonitor.get_cpu_usage()
        if cpu_usage > 10:
            activities.append(f"CPU: {cpu_usage:.1f}%")
        return ", ".join(activities) if activities else "Нет активности"