import psutil
import socket
import platform

from core.hardware_id import HardwareIDGenerator
from core.database_manager import DatabaseManager


class SystemInfoCollector:
    
    @staticmethod
    def get_basic_info() -> dict:
        return {
            "hostname": socket.gethostname(),
            "ip_address": DatabaseManager.get_local_ip(),
            "mac_address": HardwareIDGenerator.get_mac_address(),
            "os_version": f"{platform.system()} {platform.release()}"
        }
    
    @staticmethod
    def get_performance_metrics() -> dict:
        try:
            return {
                "cpu_usage": psutil.cpu_percent(interval=1),
                "ram_usage": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "disk_usage": psutil.disk_usage('/').percent,
                "disk_used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
                "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                "network_sent_mb": round(psutil.net_io_counters().bytes_sent / (1024**2), 2),
                "network_recv_mb": round(psutil.net_io_counters().bytes_recv / (1024**2), 2),
                "uptime_seconds": psutil.boot_time()
            }
        except:
            return {}