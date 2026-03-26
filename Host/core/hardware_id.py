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
            if platform.system() == "Windows":
                cmd = "wmic cpu get processorid"
                output = subprocess.check_output(cmd, shell=True).decode()
                match = re.search(r'[A-F0-9]{8,}', output)
                if match:
                    return match.group()
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
            if platform.system() == "Windows":
                cmd = "wmic diskdrive get serialnumber"
                output = subprocess.check_output(cmd, shell=True).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
        except:
            pass
        return "Unknown"
    
    @staticmethod
    def get_motherboard_serial() -> str:
        try:
            if platform.system() == "Windows":
                cmd = "wmic baseboard get serialnumber"
                output = subprocess.check_output(cmd, shell=True).decode()
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
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