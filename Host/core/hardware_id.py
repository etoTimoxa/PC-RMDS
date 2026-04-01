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
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic cpu get processorid"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                match = re.search(r'[A-F0-9]{8,}', output)
                if match:
                    return match.group()
            elif system == "Linux":
                # Try to get CPU info from /proc/cpuinfo
                try:
                    with open('/proc/cpuinfo', 'r') as f:
                        for line in f:
                            if 'model name' in line:
                                return line.split(':')[1].strip()[:32]
                except:
                    pass
                # Try dmidecode
                try:
                    output = subprocess.check_output(['dmidecode', '-s', 'processor-version'], stderr=subprocess.DEVNULL).decode().strip()
                    if output:
                        return output[:32]
                except:
                    pass
            elif system == "Darwin":
                # macOS
                try:
                    output = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], stderr=subprocess.DEVNULL).decode().strip()
                    if output:
                        return output[:32]
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_mac_address() -> str:
        try:
            mac = uuid.getnode()
            return ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))
        except:
            return "Unknown"
    
    @staticmethod
    def get_disk_serial() -> str:
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic diskdrive get serialnumber"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
            elif system == "Linux":
                # Try to get disk serial from /dev/disk/by-id or lsblk
                try:
                    output = subprocess.check_output(['lsblk', '-o', 'SERIAL', '-n'], stderr=subprocess.DEVNULL).decode().strip()
                    if output:
                        return output
                except:
                    pass
            elif system == "Darwin":
                # macOS - try diskutil
                try:
                    output = subprocess.check_output(['diskutil', 'info', 'disk0'], stderr=subprocess.DEVNULL).decode()
                    for line in output.split('\n'):
                        if 'Disk Number' in line or 'Volume UUID' in line:
                            return line.split(':')[-1].strip()
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_motherboard_serial() -> str:
        try:
            system = platform.system()
            if system == "Windows":
                cmd = "wmic baseboard get serialnumber"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
            elif system == "Linux":
                # Try dmidecode
                try:
                    output = subprocess.check_output(['dmidecode', '-s', 'baseboard-serial-number'], stderr=subprocess.DEVNULL).decode().strip()
                    if output and output != "Not Specified":
                        return output
                except:
                    pass
            elif system == "Darwin":
                # macOS - use platform UUID
                try:
                    output = subprocess.check_output(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], stderr=subprocess.DEVNULL).decode()
                    for line in output.split('\n'):
                        if 'IOPlatformSerialNumber' in line:
                            match = re.search(r'"IOPlatformSerialNumber" = "([^"]+)"', line)
                            if match:
                                return match.group(1)
                except:
                    pass
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def generate_unique_id() -> str:
        cpu = HardwareIDGenerator.get_cpu_serial()
        mac = HardwareIDGenerator.get_mac_address()
        disk = HardwareIDGenerator.get_disk_serial()
        motherboard = HardwareIDGenerator.get_motherboard_serial()
        hardware_string = f"{cpu}{mac}{disk}{motherboard}"
        return hashlib.sha256(hardware_string.encode()).hexdigest()[:32]
    
    @staticmethod
    def save_credentials(login: str, password: str) -> str:
        try:
            cred_file = os.path.expanduser("~/remote_access_credentials.txt")
            with open(cred_file, 'w') as f:
                f.write(f"=== REMOTE ACCESS CREDENTIALS ===\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Computer: {socket.gethostname()}\n")
                f.write(f"MAC Address: {HardwareIDGenerator.get_mac_address()}\n")
                f.write(f"Login: {login}\n")
                f.write(f"Password: {password}\n")
                f.write(f"Hardware ID: {HardwareIDGenerator.generate_unique_id()}\n")
            return cred_file
        except:
            return ""