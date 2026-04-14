import hashlib
import os
import platform
import re
import socket
import subprocess
import uuid
from datetime import datetime


class HardwareIDGenerator:
    
    @staticmethod
    def get_cpu_serial() -> str:
        """Получает серийный номер процессора"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic cpu get processorid"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                match = re.search(r'[A-F0-9]{8,}', output)
                if match:
                    return match.group()
            elif system == "Linux":
                try:
                    with open('/proc/cpuinfo', 'r') as f:
                        for line in f:
                            if 'model name' in line:
                                return line.split(':')[1].strip()[:32]
                except:
                    pass
            elif system == "Darwin":
                try:
                    output = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                                    stderr=subprocess.DEVNULL).decode().strip()
                    if output:
                        return output[:32]
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_cpu_model() -> str:
        """Получает читаемую модель процессора"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic cpu get name"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    model = lines[1].strip()
                    if model and model != "Name":
                        model = ' '.join(model.split())
                        return model
            elif system == "Linux":
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line:
                            model = line.split(':')[1].strip()
                            if model:
                                return model
            elif system == "Darwin":
                output = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                                stderr=subprocess.DEVNULL).decode().strip()
                if output:
                    return output
        except Exception as e:
            print(f"Ошибка получения CPU модели: {e}")
        
        try:
            return platform.processor()
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_cpu_cores() -> int:
        """Получает количество физических ядер процессора"""
        try:
            import psutil
            physical_cores = psutil.cpu_count(logical=False)
            if physical_cores:
                return physical_cores
            logical_cores = psutil.cpu_count(logical=True)
            return logical_cores or 0
        except:
            try:
                system = platform.system()
                if system == "Windows":
                    cmd = "wmic cpu get numberOfCores"
                    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                    lines = output.strip().split('\n')
                    if len(lines) > 1:
                        return int(lines[1].strip())
                elif system == "Linux":
                    with open('/proc/cpuinfo', 'r') as f:
                        cores = 0
                        for line in f:
                            if 'core id' in line:
                                cores += 1
                        return cores if cores > 0 else 0
            except:
                pass
            return 0
    
    @staticmethod
    def get_mac_address() -> str:
        """Получает MAC-адрес"""
        try:
            mac = uuid.getnode()
            mac_str = ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))
            if mac_str and mac_str != "00:00:00:00:00:00":
                return mac_str
        except:
            pass
        
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic nic where NetEnabled=true get MACAddress"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                for line in lines:
                    if re.match(r'[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}', line, re.IGNORECASE):
                        return line.strip()
            elif system == "Linux":
                import psutil
                for interface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.family == psutil.AF_LINK and addr.address:
                            return addr.address
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_disk_serial() -> str:
        """Получает серийный номер диска"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic diskdrive get serialnumber"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    serial = lines[1].strip()
                    if serial and serial != "SerialNumber":
                        return serial
            elif system == "Linux":
                try:
                    output = subprocess.check_output(['lsblk', '-o', 'SERIAL', '-n'], 
                                                    stderr=subprocess.DEVNULL).decode().strip()
                    if output:
                        return output.split('\n')[0]
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_motherboard_serial() -> str:
        """Получает серийный номер материнской платы"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic baseboard get serialnumber"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    serial = lines[1].strip()
                    invalid_values = ["", "None", "Not Specified", "NotApplicable", 
                                     "Default string", "To be filled by O.E.M.", "NA", "N/A", "0", "00000000"]
                    if serial and serial not in invalid_values:
                        return serial
            elif system == "Linux":
                try:
                    with open('/sys/devices/virtual/dmi/id/board_serial', 'r') as f:
                        serial = f.read().strip()
                        if serial and serial != "Not Specified":
                            return serial
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_motherboard_model() -> str:
        """Получает модель материнской платы"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic baseboard get product"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    model = lines[1].strip()
                    invalid_values = ["", "None", "Not Specified", "To be filled by O.E.M."]
                    if model and model not in invalid_values:
                        return model
            elif system == "Linux":
                try:
                    with open('/sys/devices/virtual/dmi/id/board_name', 'r') as f:
                        model = f.read().strip()
                        if model and model != "Not Specified":
                            return model
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_motherboard_manufacturer() -> str:
        """Получает производителя материнской платы"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic baseboard get manufacturer"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
            elif system == "Linux":
                try:
                    with open('/sys/devices/virtual/dmi/id/board_vendor', 'r') as f:
                        return f.read().strip()
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_ram_total_gb() -> float:
        """Получает общий объем RAM в ГБ"""
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024**3), 2)
        except:
            return 0.0
    
    @staticmethod
    def get_storage_total_gb() -> float:
        """Получает общий объем дискового хранилища в ГБ"""
        try:
            import psutil
            total = 0
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total += usage.total
                except:
                    pass
            return round(total / (1024**3), 2)
        except:
            return 0.0
    
    @staticmethod
    def get_gpu_model() -> str:
        """Получает модель видеокарты"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic path win32_videocontroller get name"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    for line in lines[1:]:
                        gpu = line.strip()
                        if gpu and gpu != "Name":
                            return gpu
            elif system == "Linux":
                try:
                    output = subprocess.check_output(['lspci'], stderr=subprocess.DEVNULL).decode()
                    for line in output.split('\n'):
                        if 'VGA compatible controller' in line or '3D controller' in line:
                            gpu = line.split(':')[-1].strip()
                            if gpu:
                                return gpu
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_bios_version() -> str:
        """Получает версию BIOS/UEFI"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic bios get smbiosbiosversion"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
            elif system == "Linux":
                try:
                    with open('/sys/devices/virtual/dmi/id/bios_version', 'r') as f:
                        return f.read().strip()
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_bios_manufacturer() -> str:
        """Получает производителя BIOS"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic bios get manufacturer"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_bios_name() -> str:
        """Получает название BIOS"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic bios get name"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_bios_release_date() -> str:
        """Получает дату выпуска BIOS"""
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic bios get releasedate"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    date_raw = lines[1].strip()
                    if len(date_raw) >= 8:
                        return f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_os_name() -> str:
        """Получает название операционной системы"""
        try:
            system = platform.system()
            if system == "Windows":
                return "Windows"
            elif system == "Linux":
                return "Linux"
            elif system == "Darwin":
                return "macOS"
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_os_version() -> str:
        """Получает версию операционной системы"""
        try:
            return platform.release()
        except:
            return "Unknown"
    
    @staticmethod
    def get_os_architecture() -> str:
        """Получает архитектуру ОС"""
        try:
            arch = platform.machine()
            if '64' in arch:
                return 'x64'
            elif '86' in arch or '32' in arch:
                return 'x86'
            else:
                return arch
        except:
            return "Unknown"
    
    @staticmethod
    def generate_unique_id() -> str:
        """Генерирует уникальный ID на основе характеристик железа"""
        cpu = HardwareIDGenerator.get_cpu_serial()
        mac = HardwareIDGenerator.get_mac_address()
        disk = HardwareIDGenerator.get_disk_serial()
        motherboard = HardwareIDGenerator.get_motherboard_serial()
        hardware_string = f"{cpu}{mac}{disk}{motherboard}"
        return hashlib.sha256(hardware_string.encode()).hexdigest()[:32]

    @staticmethod
    def get_hardware_id() -> str:
        """Алиас для совместимости со старым кодом"""
        return HardwareIDGenerator.generate_unique_id()
    
    @staticmethod
    def get_full_hardware_info() -> dict:
        """Возвращает полную информацию о железе компьютера"""
        now = datetime.now().isoformat()
        return {
            # Основная информация для hardware_config
            "cpu_model": HardwareIDGenerator.get_cpu_model(),
            "cpu_cores": HardwareIDGenerator.get_cpu_cores(),
            "ram_total": HardwareIDGenerator.get_ram_total_gb(),
            "storage_total": HardwareIDGenerator.get_storage_total_gb(),
            "gpu_model": HardwareIDGenerator.get_gpu_model(),
            "motherboard": HardwareIDGenerator.get_motherboard_model(),
            "bios_version": HardwareIDGenerator.get_bios_version(),
            
            # Дополнительная информация
            "cpu_serial": HardwareIDGenerator.get_cpu_serial(),
            "motherboard_manufacturer": HardwareIDGenerator.get_motherboard_manufacturer(),
            "motherboard_serial": HardwareIDGenerator.get_motherboard_serial(),
            "bios_manufacturer": HardwareIDGenerator.get_bios_manufacturer(),
            "bios_name": HardwareIDGenerator.get_bios_name(),
            "bios_release_date": HardwareIDGenerator.get_bios_release_date(),
            "disk_serial": HardwareIDGenerator.get_disk_serial(),
            "mac_address": HardwareIDGenerator.get_mac_address(),
            "hardware_id": HardwareIDGenerator.generate_unique_id(),
            
            # Информация об ОС
            "os_name": HardwareIDGenerator.get_os_name(),
            "os_version": HardwareIDGenerator.get_os_version(),
            "os_architecture": HardwareIDGenerator.get_os_architecture(),
            
            "detected_at": now,
            "updated_at": now
        }

    @staticmethod
    def save_credentials(login: str, password: str) -> str:
        """Сохраняет учетные данные в файл"""
        try:
            from utils.platform_utils import get_config_dir
            config_dir = get_config_dir()
            cred_file = config_dir / "credentials.txt"
            cred_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(cred_file, 'w', encoding='utf-8') as f:
                f.write(f"=== REMOTE ACCESS CREDENTIALS ===\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Computer: {socket.gethostname()}\n")
                f.write(f"MAC Address: {HardwareIDGenerator.get_mac_address()}\n")
                f.write(f"Login: {login}\n")
                f.write(f"Password: {password}\n")
                f.write(f"Hardware ID: {HardwareIDGenerator.generate_unique_id()}\n")
                f.write(f"CPU: {HardwareIDGenerator.get_cpu_model()}\n")
                f.write(f"RAM: {HardwareIDGenerator.get_ram_total_gb()} GB\n")
                f.write(f"Disk: {HardwareIDGenerator.get_storage_total_gb()} GB\n")
            return str(cred_file)
        except:
            return ""