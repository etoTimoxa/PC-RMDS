import sys
import asyncio
import websockets
import json
import mss
from io import BytesIO
from PIL import Image
import base64
import time
import platform
import psutil
import socket
from datetime import datetime
import pyautogui
import os
import hashlib
import pymysql
import uuid
import subprocess
import re
import winreg
import signal
import atexit
import ctypes
from typing import Optional, Dict, Any
import win32api
import win32con
from ctypes import wintypes

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTextEdit, QGroupBox, QGridLayout, QMessageBox,
                            QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
                            QSpinBox, QDoubleSpinBox, QTabWidget, QSystemTrayIcon,
                            QMenu, QStatusBar, QFrame, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QAction, QIcon, QPixmap, QColor

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController


# Глобальная переменная для очистки
_cleanup_done = False

def cleanup_on_exit():
    """Функция для очистки при завершении"""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    
    try:
        if hasattr(DatabaseManager, 'current_session_id') and DatabaseManager.current_session_id:
            if hasattr(DatabaseManager, 'current_computer_id'):
                DatabaseManager.update_computer_status(
                    DatabaseManager.current_computer_id, 
                    False, 
                    DatabaseManager.current_session_id
                )
    except:
        pass

# Регистрируем функцию очистки
atexit.register(cleanup_on_exit)

# Обработка сигналов
def signal_handler(signum, frame):
    """Обработчик сигналов"""
    cleanup_on_exit()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, signal_handler)


# Стили для приложения
APP_STYLE = """
QMainWindow {
    background-color: #f5f5f5;
}

QGroupBox {
    font-weight: bold;
    border: 2px solid #ff8c42;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    background-color: white;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px 0 5px;
    color: #ff8c42;
}

QLabel {
    color: #333333;
}

QPushButton {
    background-color: #ff8c42;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #ff6b2c;
}
QPushButton:pressed {
    background-color: #e55a1a;
}
QPushButton:disabled {
    background-color: #cccccc;
    color: #666666;
}

QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
    border: 1px solid #ff8c42;
    border-radius: 4px;
    padding: 5px;
    background-color: white;
}
QLineEdit:focus, QTextEdit:focus {
    border: 2px solid #ff8c42;
}

QTabWidget::pane {
    border: 1px solid #ff8c42;
    border-radius: 4px;
    background-color: white;
}
QTabBar::tab {
    background-color: #e0e0e0;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #ff8c42;
    color: white;
}
QTabBar::tab:hover:!selected {
    background-color: #ffb87a;
}

QProgressBar {
    border: 1px solid #ff8c42;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #ff8c42;
    border-radius: 3px;
}

QStatusBar {
    background-color: #f0f0f0;
    color: #666666;
}

QMenuBar {
    background-color: #ff8c42;
    color: white;
}
QMenuBar::item {
    background-color: #ff8c42;
    padding: 4px 8px;
}
QMenuBar::item:selected {
    background-color: #ff6b2c;
}
QMenu {
    background-color: white;
    border: 1px solid #ff8c42;
}
QMenu::item:selected {
    background-color: #ff8c42;
    color: white;
}

QSystemTrayIcon {
    color: #ff8c42;
}
"""


class SystemActivityMonitor:
    """Мониторинг активности системы"""
    
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    
    @staticmethod
    def get_last_input_time():
        """Получить время последнего ввода (мышь/клавиатура) в секундах"""
        try:
            lastInputInfo = SystemActivityMonitor.LASTINPUTINFO()
            lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo))
            tickCount = ctypes.windll.kernel32.GetTickCount()
            elapsed_ms = tickCount - lastInputInfo.dwTime
            return elapsed_ms / 1000.0
        except:
            return 0
    
    @staticmethod
    def get_cpu_usage():
        """Получить текущую загрузку CPU"""
        try:
            return psutil.cpu_percent(interval=1)
        except:
            return 0
    
    @staticmethod
    def get_memory_usage():
        """Получить использование памяти"""
        try:
            return psutil.virtual_memory().percent
        except:
            return 0
    
    @staticmethod
    def get_disk_io():
        """Получить активность диска (MB)"""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                return (disk_io.read_bytes + disk_io.write_bytes) / (1024 * 1024)
            return 0
        except:
            return 0
    
    @staticmethod
    def get_network_activity():
        """Получить сетевую активность (MB)"""
        try:
            net_io = psutil.net_io_counters()
            if net_io:
                return (net_io.bytes_recv + net_io.bytes_sent) / (1024 * 1024)
            return 0
        except:
            return 0
    
    @staticmethod
    def get_running_processes():
        """Получить список активных процессов"""
        try:
            active_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    if proc.info['cpu_percent'] > 5 or proc.info['memory_percent'] > 10:
                        active_processes.append({
                            'name': proc.info['name'],
                            'cpu': proc.info['cpu_percent'],
                            'memory': proc.info['memory_percent']
                        })
                except:
                    pass
            return active_processes[:5]
        except:
            return []
    
    @staticmethod
    def get_active_windows():
        """Получить активные окна Windows"""
        try:
            import win32gui
            
            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if window_text:
                        windows.append(window_text)
                return True
            
            windows = []
            win32gui.EnumWindows(callback, windows)
            return windows[:5]
        except:
            return []
    
    @staticmethod
    def is_system_active():
        """Определить, активна ли система"""
        last_input = SystemActivityMonitor.get_last_input_time()
        if last_input < 300:
            return True
        
        cpu_usage = SystemActivityMonitor.get_cpu_usage()
        if cpu_usage > 10:
            return True
        
        disk_io = SystemActivityMonitor.get_disk_io()
        if disk_io > 50:
            return True
        
        net_activity = SystemActivityMonitor.get_network_activity()
        if net_activity > 20:
            return True
        
        processes = SystemActivityMonitor.get_running_processes()
        if processes:
            return True
        
        return False
    
    @staticmethod
    def get_activity_description():
        """Получить описание текущей активности"""
        activities = []
        
        last_input = SystemActivityMonitor.get_last_input_time()
        if last_input < 300:
            activities.append(f"Ввод: {int(last_input)} сек назад")
        
        cpu_usage = SystemActivityMonitor.get_cpu_usage()
        if cpu_usage > 10:
            activities.append(f"CPU: {cpu_usage:.1f}%")
        
        disk_io = SystemActivityMonitor.get_disk_io()
        if disk_io > 50:
            activities.append(f"Диск: {disk_io:.0f} MB")
        
        net_activity = SystemActivityMonitor.get_network_activity()
        if net_activity > 20:
            activities.append(f"Сеть: {net_activity:.0f} MB")
        
        processes = SystemActivityMonitor.get_running_processes()
        if processes:
            activities.append(f"Процессы: {len(processes)}")
        
        windows = SystemActivityMonitor.get_active_windows()
        if windows:
            activities.append(f"Окна: {windows[0][:20]}...")
        
        if activities:
            return ", ".join(activities[:3])
        return "Нет активности"


class HardwareIDGenerator:
    """Генератор уникального идентификатора компьютера"""
    
    @staticmethod
    def get_cpu_serial():
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
    def get_mac_address():
        try:
            mac = uuid.getnode()
            return ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))
        except:
            return "Unknown"
    
    @staticmethod
    def get_disk_serial():
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
    def get_motherboard_serial():
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
    def generate_unique_id():
        cpu = HardwareIDGenerator.get_cpu_serial()
        mac = HardwareIDGenerator.get_mac_address()
        disk = HardwareIDGenerator.get_disk_serial()
        motherboard = HardwareIDGenerator.get_motherboard_serial()
        
        hardware_string = f"{cpu}{mac}{disk}{motherboard}"
        unique_id = hashlib.sha256(hardware_string.encode()).hexdigest()
        
        return unique_id[:32]
    
    @staticmethod
    def save_credentials(login: str, password: str):
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
            return None


class DatabaseManager:
    """Класс для работы с базой данных"""
    
    DB_CONFIG = {
        'host': '5.183.188.132',
        'user': '2024_mysql_t_usr',
        'password': 'uqnOzz3fbUqudcdM',
        'db': '2024_mysql_tim',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
    
    current_session_id = None
    current_computer_id = None
    
    @staticmethod
    def get_connection():
        try:
            return pymysql.connect(**DatabaseManager.DB_CONFIG)
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None
    
    @staticmethod
    def set_current_session(computer_id, session_id):
        """Сохранить текущую сессию для очистки при завершении"""
        DatabaseManager.current_computer_id = computer_id
        DatabaseManager.current_session_id = session_id
    
    @staticmethod
    def create_session(computer_id: int) -> Optional[int]:
        connection = DatabaseManager.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE client_session 
                    SET status_id = 3, end_time = NOW()
                    WHERE computer_id = %s AND status_id IN (1, 2)
                """, (computer_id,))
                
                session_token = hashlib.sha256(
                    f"{computer_id}{datetime.now().isoformat()}{uuid.uuid4()}".encode()
                ).hexdigest()
                
                cursor.execute("""
                    INSERT INTO client_session 
                    (computer_id, session_token, start_ip, start_method, status_id, last_heartbeat)
                    VALUES (%s, %s, %s, 'auto_auth', 1, NOW())
                """, (computer_id, session_token, DatabaseManager.get_local_ip()))
                
                session_id = cursor.lastrowid
                connection.commit()
                return session_id
        except Exception as e:
            print(f"Ошибка создания сессии: {e}")
            return None
        finally:
            connection.close()
    
    @staticmethod
    def update_heartbeat(session_id: int):
        """Обновить heartbeat сессии"""
        connection = DatabaseManager.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE client_session 
                    SET last_heartbeat = NOW()
                    WHERE session_id = %s
                """, (session_id,))
                connection.commit()
        except:
            pass
        finally:
            connection.close()
    
    @staticmethod
    def get_or_create_os():
        connection = DatabaseManager.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                os_name = platform.system()
                os_version = platform.release()
                os_build = None
                
                if platform.system() == "Windows":
                    try:
                        os_build = platform.version()
                    except:
                        pass
                
                os_arch = platform.machine()
                if os_arch == "AMD64":
                    os_arch = "x64"
                elif os_arch == "ARM64":
                    os_arch = "arm64"
                else:
                    os_arch = "x86"
                
                cursor.execute("""
                    SELECT os_id FROM operating_system 
                    WHERE os_name = %s AND os_version = %s
                """, (os_name, os_version))
                
                os_record = cursor.fetchone()
                
                if os_record:
                    return os_record['os_id']
                else:
                    cursor.execute("""
                        INSERT INTO operating_system 
                        (os_name, os_version, os_build, os_architecture, is_supported)
                        VALUES (%s, %s, %s, %s, 1)
                    """, (os_name, os_version, os_build, os_arch))
                    
                    os_id = cursor.lastrowid
                    connection.commit()
                    return os_id
        except:
            return None
        finally:
            connection.close()
    
    @staticmethod
    def update_ip_address(computer_id: int, ip_address: str):
        """Обновить IP адрес компьютера"""
        connection = DatabaseManager.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT ip_address, ip_id FROM ip_address 
                    WHERE computer_id = %s AND is_current = 1
                """, (computer_id,))
                
                current_ip = cursor.fetchone()
                
                if current_ip and current_ip['ip_address'] == ip_address:
                    return current_ip['ip_id']
                
                if current_ip:
                    cursor.execute("""
                        UPDATE ip_address SET is_current = 0
                        WHERE computer_id = %s AND is_current = 1
                    """, (computer_id,))
                
                cursor.execute("""
                    INSERT INTO ip_address 
                    (computer_id, ip_address, interface_name, is_current, detected_at)
                    VALUES (%s, %s, %s, 1, NOW())
                """, (computer_id, ip_address, "Ethernet"))
                
                ip_id = cursor.lastrowid
                
                cursor.execute("""
                    UPDATE computer SET ip_address_id = %s
                    WHERE computer_id = %s
                """, (ip_id, computer_id))
                
                connection.commit()
                return ip_id
        except:
            return None
        finally:
            connection.close()
    
    @staticmethod
    def update_hardware_config(computer_id: int):
        """Обновить конфигурацию оборудования"""
        connection = DatabaseManager.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cpu_model = platform.processor() or "Unknown"
                cpu_cores = psutil.cpu_count(logical=True)
                ram = psutil.virtual_memory()
                ram_total = round(ram.total / (1024**3), 2)
                disk = psutil.disk_usage('/')
                storage_total = round(disk.total / (1024**3), 2)
                
                gpu_model = "Unknown"
                if platform.system() == "Windows":
                    try:
                        cmd = "wmic path win32_VideoController get name"
                        output = subprocess.check_output(cmd, shell=True).decode()
                        lines = output.strip().split('\n')
                        if len(lines) > 1:
                            gpu_model = lines[1].strip()
                    except:
                        pass
                
                cursor.execute("""
                    SELECT cpu_model, cpu_cores, ram_total, storage_total, gpu_model 
                    FROM hardware_config
                    WHERE computer_id = %s
                """, (computer_id,))
                
                current = cursor.fetchone()
                
                if current:
                    if (current['cpu_model'] == cpu_model and 
                        current['cpu_cores'] == cpu_cores and
                        current['ram_total'] == ram_total and
                        current['storage_total'] == storage_total and
                        current['gpu_model'] == gpu_model):
                        return
                
                if current:
                    cursor.execute("""
                        UPDATE hardware_config 
                        SET cpu_model = %s, cpu_cores = %s, ram_total = %s, 
                            storage_total = %s, gpu_model = %s, updated_at = NOW()
                        WHERE computer_id = %s
                    """, (cpu_model, cpu_cores, ram_total, storage_total, gpu_model, computer_id))
                else:
                    cursor.execute("""
                        INSERT INTO hardware_config 
                        (computer_id, cpu_model, cpu_cores, ram_total, storage_total, gpu_model)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (computer_id, cpu_model, cpu_cores, ram_total, storage_total, gpu_model))
                
                connection.commit()
        except:
            pass
        finally:
            connection.close()
    
    @staticmethod
    def register_computer() -> Optional[Dict[str, Any]]:
        connection = DatabaseManager.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                hostname = socket.gethostname()
                mac_address = HardwareIDGenerator.get_mac_address()
                unique_hardware_id = HardwareIDGenerator.generate_unique_id()
                
                computer_login = f"comp_{unique_hardware_id[:16]}"
                computer_password = unique_hardware_id
                password_hash = hashlib.sha256(computer_password.encode()).hexdigest()
                
                cursor.execute("""
                    SELECT c.computer_id, c.hostname, c.mac_address, cred.login, cred.password_hash
                    FROM computer c
                    INNER JOIN credential cred ON c.credential_id = cred.credential_id
                    WHERE c.mac_address = %s
                """, (mac_address,))
                
                existing = cursor.fetchone()
                
                if existing:
                    if existing['password_hash'] == password_hash:
                        if existing['hostname'] != hostname:
                            cursor.execute("""
                                UPDATE computer SET hostname = %s
                                WHERE computer_id = %s
                            """, (hostname, existing['computer_id']))
                            connection.commit()
                        
                        ip_address = DatabaseManager.get_local_ip()
                        DatabaseManager.update_ip_address(existing['computer_id'], ip_address)
                        DatabaseManager.update_hardware_config(existing['computer_id'])
                        
                        session_id = DatabaseManager.create_session(existing['computer_id'])
                        
                        return {
                            'computer_id': existing['computer_id'],
                            'hostname': hostname,
                            'mac_address': existing['mac_address'],
                            'login': existing['login'],
                            'password': computer_password,
                            'is_new': False,
                            'session_id': session_id
                        }
                    return None
                
                cursor.execute("""
                    INSERT INTO credential (login, password_hash, credential_type, is_active)
                    VALUES (%s, %s, 'computer', 1)
                """, (computer_login, password_hash))
                credential_id = cursor.lastrowid
                
                os_id = DatabaseManager.get_or_create_os()
                
                cursor.execute("""
                    INSERT INTO computer 
                    (credential_id, os_id, hostname, mac_address, is_online, first_seen, last_online)
                    VALUES (%s, %s, %s, %s, 1, NOW(), NOW())
                """, (credential_id, os_id, hostname, mac_address))
                computer_id = cursor.lastrowid
                
                connection.commit()
                
                ip_address = DatabaseManager.get_local_ip()
                DatabaseManager.update_ip_address(computer_id, ip_address)
                DatabaseManager.update_hardware_config(computer_id)
                
                session_id = DatabaseManager.create_session(computer_id)
                HardwareIDGenerator.save_credentials(computer_login, computer_password)
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'login': computer_login,
                    'password': computer_password,
                    'is_new': True,
                    'session_id': session_id
                }
        except:
            return None
        finally:
            connection.close()
    
    @staticmethod
    def authenticate_computer() -> Optional[Dict[str, Any]]:
        unique_id = HardwareIDGenerator.generate_unique_id()
        computer_login = f"comp_{unique_id[:16]}"
        computer_password = unique_id
        password_hash = hashlib.sha256(computer_password.encode()).hexdigest()
        
        connection = DatabaseManager.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        c.computer_id, c.hostname, c.mac_address,
                        cred.credential_id, cred.login,
                        os.os_name, os.os_version
                    FROM credential cred
                    INNER JOIN computer c ON c.credential_id = cred.credential_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    WHERE cred.login = %s AND cred.password_hash = %s
                        AND cred.credential_type = 'computer' AND cred.is_active = 1
                """, (computer_login, password_hash))
                
                computer_data = cursor.fetchone()
                
                if computer_data:
                    hostname = socket.gethostname()
                    if computer_data['hostname'] != hostname:
                        cursor.execute("""
                            UPDATE computer SET hostname = %s
                            WHERE computer_id = %s
                        """, (hostname, computer_data['computer_id']))
                        connection.commit()
                    
                    ip_address = DatabaseManager.get_local_ip()
                    DatabaseManager.update_ip_address(computer_data['computer_id'], ip_address)
                    DatabaseManager.update_hardware_config(computer_data['computer_id'])
                    
                    session_id = DatabaseManager.create_session(computer_data['computer_id'])
                    
                    return {
                        'computer_id': computer_data['computer_id'],
                        'hostname': hostname,
                        'mac_address': computer_data['mac_address'],
                        'login': computer_data['login'],
                        'os_name': computer_data.get('os_name', 'Unknown'),
                        'os_version': computer_data.get('os_version', 'Unknown'),
                        'session_id': session_id,
                        'is_new': False
                    }
                return None
        except:
            return None
        finally:
            connection.close()
    
    @staticmethod
    def update_computer_status(computer_id: int, is_online: bool, session_id: int = None):
        """Обновить статус компьютера и завершить сессию"""
        connection = DatabaseManager.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE computer SET is_online = %s, last_online = NOW()
                    WHERE computer_id = %s
                """, (1 if is_online else 0, computer_id))
                
                if session_id:
                    cursor.execute("""
                        UPDATE client_session 
                        SET status_id = 3, end_time = NOW()
                        WHERE session_id = %s
                    """, (session_id,))
                elif not is_online:
                    cursor.execute("""
                        UPDATE client_session 
                        SET status_id = 3, end_time = NOW()
                        WHERE computer_id = %s AND status_id IN (1, 2)
                    """, (computer_id,))
                
                connection.commit()
        except:
            pass
        finally:
            connection.close()
    
    @staticmethod
    def update_session_activity(session_id: int, data_sent: int = 0, data_received: int = 0, 
                                force: bool = False, activity_desc: str = None):
        """Обновить активность сессии"""
        connection = DatabaseManager.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                if force or data_sent > 0 or data_received > 0:
                    cursor.execute("""
                        UPDATE client_session 
                        SET last_activity = NOW(),
                            last_heartbeat = NOW(),
                            data_sent = data_sent + %s,
                            data_received = data_received + %s
                        WHERE session_id = %s
                    """, (data_sent, data_received, session_id))
                else:
                    cursor.execute("""
                        UPDATE client_session 
                        SET last_activity = NOW(),
                            last_heartbeat = NOW()
                        WHERE session_id = %s
                    """, (session_id,))
                
                connection.commit()
        except:
            pass
        finally:
            connection.close()
    
    @staticmethod
    def save_metrics(computer_id: int, session_id: int, metrics: Dict):
        connection = DatabaseManager.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO metric 
                    (computer_id, session_id, cpu_usage, ram_usage, disk_usage, timestamp)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (
                    computer_id, session_id,
                    metrics.get('cpu_usage', 0),
                    metrics.get('ram_usage', 0),
                    metrics.get('disk_usage', 0)
                ))
                
                cursor.execute("""
                    UPDATE client_session 
                    SET metrics_count = metrics_count + 1,
                        last_activity = NOW()
                    WHERE session_id = %s
                """, (session_id,))
                
                connection.commit()
        except:
            pass
        finally:
            connection.close()
    
    @staticmethod
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"


class AutoAuthDialog(QDialog):
    """Диалог автоматической авторизации"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_success = False
        self.computer_data = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        self.setFixedSize(450, 350)
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
            QLabel {
                color: #333333;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 15px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        
        layout.addWidget(title_frame)
        
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid #ff8c42; border-radius: 8px; padding: 15px;")
        info_layout = QVBoxLayout(info_frame)
        
        computer_name = socket.gethostname()
        info_text = f"""
        <div style='text-align: center;'>
            <h3 style='color: #ff8c42;'>Автоматическая регистрация</h3>
            <p><b>Компьютер:</b> {computer_name}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
            <p><b>Статус:</b> Выполняется регистрация...</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        
        layout.addWidget(info_frame)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ff8c42;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #ff8c42;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Регистрация...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)
        
        QTimer.singleShot(500, self.register)
    
    def register(self):
        self.status_label.setText("Проверка регистрации...")
        QTimer.singleShot(100, self.do_register)
    
    def do_register(self):
        try:
            computer_data = DatabaseManager.authenticate_computer()
            
            if not computer_data:
                self.status_label.setText("Регистрация нового компьютера...")
                computer_data = DatabaseManager.register_computer()
            
            if computer_data:
                self.computer_data = computer_data
                self.auth_success = True
                self.status_label.setText("✓ Регистрация успешна!")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                
                if computer_data.get('is_new'):
                    QMessageBox.information(
                        self,
                        "Регистрация успешна",
                        f"Компьютер зарегистрирован!\n\n"
                        f"ID: {computer_data['computer_id']}\n"
                        f"Логин: {computer_data['login']}\n\n"
                        f"Данные сохранены в:\n~/remote_access_credentials.txt"
                    )
                
                QTimer.singleShot(1000, self.accept)
            else:
                self.status_label.setText("✗ Ошибка подключения к БД")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                QTimer.singleShot(3000, self.reject)
                
        except Exception as e:
            self.status_label.setText(f"✗ Ошибка: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            QTimer.singleShot(3000, self.reject)


class SettingsDialog(QDialog):
    """Диалог настроек"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(450)
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        tab_widget = QTabWidget()
        
        conn_tab = QWidget()
        conn_layout = QFormLayout(conn_tab)
        
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("ws://127.0.0.1:9001")
        conn_layout.addRow("Сервер:", self.server_edit)
        
        tab_widget.addTab(conn_tab, "Подключение")
        
        stream_tab = QWidget()
        stream_layout = QFormLayout(stream_tab)
        
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(30, 100)
        self.quality_spin.setSuffix("%")
        stream_layout.addRow("Качество JPEG:", self.quality_spin)
        
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setSingleStep(1)
        self.fps_spin.setSuffix(" FPS")
        stream_layout.addRow("Частота кадров:", self.fps_spin)
        
        tab_widget.addTab(stream_tab, "Трансляция")
        
        system_tab = QWidget()
        system_layout = QFormLayout(system_tab)
        
        self.auto_start_check = QCheckBox("Запускать при загрузке Windows")
        system_layout.addRow(self.auto_start_check)
        
        self.minimize_to_tray_check = QCheckBox("Сворачивать в трей при закрытии")
        system_layout.addRow(self.minimize_to_tray_check)
        
        self.auto_reconnect_check = QCheckBox("Автоматически подключаться к серверу")
        system_layout.addRow(self.auto_reconnect_check)
        
        self.disconnect_btn = QPushButton("🔌 ОТКЛЮЧИТЬСЯ ОТ СЕРВЕРА")
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                padding: 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        system_layout.addRow(self.disconnect_btn)
        
        tab_widget.addTab(system_tab, "Система")
        
        layout.addWidget(tab_widget)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def load_settings(self):
        settings = QSettings("RemoteAccess", "Agent")
        self.server_edit.setText(settings.value("server", "ws://localhost:9001"))
        self.quality_spin.setValue(int(settings.value("quality", 70)))
        self.fps_spin.setValue(float(settings.value("fps", 20)))
        self.auto_start_check.setChecked(settings.value("auto_start", True, type=bool))
        self.minimize_to_tray_check.setChecked(settings.value("minimize_to_tray", True, type=bool))
        self.auto_reconnect_check.setChecked(settings.value("auto_reconnect", True, type=bool))
    
    def save_settings(self):
        settings = QSettings("RemoteAccess", "Agent")
        settings.setValue("server", self.server_edit.text())
        settings.setValue("quality", self.quality_spin.value())
        settings.setValue("fps", self.fps_spin.value())
        settings.setValue("auto_start", self.auto_start_check.isChecked())
        settings.setValue("minimize_to_tray", self.minimize_to_tray_check.isChecked())
        settings.setValue("auto_reconnect", self.auto_reconnect_check.isChecked())
        
        if self.auto_start_check.isChecked():
            self.add_to_startup()
        else:
            self.remove_from_startup()
    
    def add_to_startup(self):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "RemoteAccessAgent", 0, winreg.REG_SZ, sys.executable + " " + __file__)
            winreg.CloseKey(key)
        except:
            pass
    
    def remove_from_startup(self):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, "RemoteAccessAgent")
            winreg.CloseKey(key)
        except:
            pass


class SystemInfoCollector:
    @staticmethod
    def get_basic_info():
        return {
            "hostname": socket.gethostname(),
            "ip_address": DatabaseManager.get_local_ip(),
            "mac_address": HardwareIDGenerator.get_mac_address(),
            "os_version": f"{platform.system()} {platform.release()}"
        }
    
    @staticmethod
    def get_hardware_config():
        try:
            return {
                "cpu_model": platform.processor() or "Unknown",
                "cpu_cores": psutil.cpu_count(logical=True),
                "ram_total": round(psutil.virtual_memory().total / (1024**3), 2),
                "storage_total": round(psutil.disk_usage('/').total / (1024**3), 2),
                "gpu_model": "Unknown"
            }
        except:
            return {}
    
    @staticmethod
    def get_performance_metrics():
        try:
            return {
                "cpu_usage": psutil.cpu_percent(interval=0.5),
                "ram_usage": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "disk_usage": psutil.disk_usage('/').percent,
                "disk_used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
                "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                "timestamp": datetime.now().isoformat()
            }
        except:
            return {}


class RemoteAgentThread(QThread):
    log_message = pyqtSignal(str)
    connection_status_changed = pyqtSignal(bool, int)
    client_connected = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    activity_status = pyqtSignal(str)
    
    def __init__(self, relay_server, computer_data, screenshot_interval, quality=70):
        super().__init__()
        self.relay_server = relay_server
        self.computer_data = computer_data
        self.computer_id = computer_data['computer_id']  # Числовой ID из БД
        self.session_id = computer_data['session_id']
        self.hostname = computer_data['hostname']
        self.screenshot_interval = screenshot_interval
        self.quality = quality
        self.is_running = True
        self.is_connected = False
        self.connected_clients = 0
        self.connected_clients_list = []
        self.streaming_clients = set()
        self.ws = None
        self.sending_screenshots = False
        self.heartbeat_task = None
        self.activity_task = None
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        try:
            self.screen_width, self.screen_height = pyautogui.size()
        except:
            self.screen_width, self.screen_height = 1920, 1080
        
        self.KEY_MAPPING = {
            'enter': Key.enter, 'space': Key.space, 'tab': Key.tab,
            'backspace': Key.backspace, 'escape': Key.esc, 'esc': Key.esc,
            'up': Key.up, 'down': Key.down, 'left': Key.left, 'right': Key.right,
            'delete': Key.delete, 'home': Key.home, 'end': Key.end,
        }
    
    def update_settings(self, screenshot_interval=None, quality=None):
        if screenshot_interval is not None:
            self.screenshot_interval = screenshot_interval
        if quality is not None:
            self.quality = quality
    
    def run(self):
        asyncio.run(self.agent_main())
    
    def start_heartbeat_updater(self):
        """Запускает периодическое обновление heartbeat (каждые 10 минут)"""
        async def update_heartbeat_periodically():
            while self.is_connected and self.is_running:
                try:
                    await asyncio.sleep(600)  # 10 минут
                    if self.is_connected and self.session_id:
                        DatabaseManager.update_heartbeat(self.session_id)
                        self.log_message.emit("Обновлен heartbeat сессии")
                except:
                    pass
        
        self.heartbeat_task = asyncio.create_task(update_heartbeat_periodically())
    
    def start_activity_updater(self):
        """Запускает периодическое обновление активности (каждые 15 минут)"""
        async def update_activity_periodically():
            while self.is_connected and self.is_running:
                try:
                    await asyncio.sleep(900)  # 15 минут
                    
                    if self.is_connected and self.session_id:
                        is_active = SystemActivityMonitor.is_system_active()
                        activity_desc = SystemActivityMonitor.get_activity_description()
                        
                        if is_active:
                            DatabaseManager.update_session_activity(
                                self.session_id, 
                                force=True,
                                activity_desc=activity_desc
                            )
                            self.activity_status.emit(f"🟢 Система активна: {activity_desc}")
                            self.log_message.emit(f"Обновлена активность: {activity_desc}")
                        else:
                            self.activity_status.emit("🟡 Система неактивна")
                            self.log_message.emit("Система неактивна")
                            
                except Exception as e:
                    self.log_message.emit(f"Ошибка обновления активности: {e}")
        
        self.activity_task = asyncio.create_task(update_activity_periodically())
    
    def stop_updaters(self):
        """Останавливает периодические обновления"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.activity_task:
            self.activity_task.cancel()
    
    async def agent_main(self):
        reconnect_delay = 5
        while self.is_running:
            try:
                async with websockets.connect(self.relay_server) as ws:
                    self.ws = ws
                    
                    # Запускаем обновления
                    self.start_heartbeat_updater()
                    self.start_activity_updater()
                    
                    # Регистрация агента с числовым computer_id
                    register_msg = {
                        "type": "register_agent",
                        "data": {
                            "computer_id": self.computer_id,
                            "session_id": self.session_id,
                            "agent_id": self.hostname,
                            "hostname": self.hostname
                        }
                    }
                    await ws.send(json.dumps(register_msg))
                    self.log_message.emit(f"Регистрация агента: computer_id={self.computer_id}")
                    
                    self.is_connected = True
                    self.connection_status_changed.emit(True, self.connected_clients)
                    self.log_message.emit(f"Подключен к серверу")
                    
                    await self.receive_commands(ws)
                    
            except Exception as e:
                self.log_message.emit(f"Ошибка: {e}")
            
            self.is_connected = False
            self.connection_status_changed.emit(False, 0)
            
            # Останавливаем обновления
            self.stop_updaters()
            
            if self.is_running:
                await asyncio.sleep(reconnect_delay)
    
    async def send_system_info(self, ws):
        try:
            system_info = {
                "basic": SystemInfoCollector.get_basic_info(),
                "hardware": SystemInfoCollector.get_hardware_config(),
                "metrics": SystemInfoCollector.get_performance_metrics(),
                "timestamp": datetime.now().isoformat(),
                "computer_id": self.computer_id,  # Используем числовой ID
                "session_id": self.session_id
            }
            
            metrics = system_info["metrics"]
            DatabaseManager.save_metrics(self.computer_id, self.session_id, metrics)
            
            message = {
                "type": "system_info",
                "data": system_info,
                "computer_id": self.computer_id,  # Используем числовой ID
                "agent_id": self.hostname
            }
            
            await ws.send(json.dumps(message))
            self.log_message.emit(f"Отправлена system_info: computer_id={self.computer_id}")
            return True
        except Exception as e:
            self.log_message.emit(f"Ошибка отправки system_info: {e}")
            return False
    
    async def screenshot_loop(self, ws):
        self.sending_screenshots = True
        frame_count = 0
        
        while self.sending_screenshots and self.is_connected and len(self.streaming_clients) > 0:
            try:
                start_time = time.time()
                
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", quality=self.quality, optimize=True)
                    img_data = buffer.getvalue()
                    img_b64 = base64.b64encode(img_data).decode()
                    
                    message = {
                        "type": "screenshot",
                        "data": img_b64,
                        "computer_id": self.computer_id,  # Используем числовой ID
                        "agent_id": self.hostname
                    }
                    
                    await ws.send(json.dumps(message))
                    frame_count += 1
                    
                    if frame_count % 30 == 0:
                        DatabaseManager.update_session_activity(self.session_id, data_sent=len(img_data))
                
                elapsed = time.time() - start_time
                sleep_time = max(0, self.screenshot_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                self.log_message.emit(f"Ошибка в screenshot_loop: {e}")
                break
        
        self.sending_screenshots = False
    
    async def receive_commands(self, ws):
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                client_id = data.get("client_id", "unknown")
                
                self.log_message.emit(f"Получена команда: {cmd_type} от {client_id}")
                
                if cmd_type == "register_client":
                    if client_id not in self.connected_clients_list:
                        self.connected_clients += 1
                        self.connected_clients_list.append(client_id)
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_connected.emit(client_id)
                        await self.send_system_info(ws)
                
                elif cmd_type == "start_stream":
                    self.streaming_clients.add(client_id)
                    self.log_message.emit(f"Клиент {client_id} начал стриминг")
                    
                    if not self.sending_screenshots and len(self.streaming_clients) > 0:
                        asyncio.create_task(self.screenshot_loop(ws))
                
                elif cmd_type == "stop_stream":
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                        self.log_message.emit(f"Клиент {client_id} остановил стриминг")
                    
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                
                elif cmd_type == "request_system_info":
                    self.log_message.emit(f"Запрос system_info от {client_id}")
                    await self.send_system_info(ws)
                
                elif cmd_type == "mouse_move":
                    await self.handle_mouse_move(data.get("data", {}))
                
                elif cmd_type == "mouse_click":
                    await self.handle_mouse_click(data.get("data", {}))
                
                elif cmd_type == "mouse_wheel":
                    await self.handle_mouse_wheel(data.get("data", {}))
                
                elif cmd_type == "keyboard_input":
                    await self.handle_keyboard_input(data.get("data", {}))
                
                DatabaseManager.update_session_activity(self.session_id, data_received=len(msg))
                    
        except Exception as e:
            self.log_message.emit(f"Ошибка в receive_commands: {e}")
    
    async def handle_mouse_move(self, command_data):
        try:
            x = command_data.get("x")
            y = command_data.get("y")
            if x is not None and y is not None:
                self.mouse.position = (x, y)
        except:
            pass
    
    async def handle_mouse_click(self, command_data):
        try:
            button_name = command_data.get("button", "left")
            x = command_data.get("x")
            y = command_data.get("y")
            
            if x is not None and y is not None:
                self.mouse.position = (x, y)
                time.sleep(0.01)
            
            button = Button.left if button_name == "left" else Button.right
            self.mouse.click(button)
        except:
            pass
    
    async def handle_mouse_wheel(self, command_data):
        try:
            delta = command_data.get("delta", 0)
            self.mouse.scroll(0, delta)
        except:
            pass
    
    async def handle_keyboard_input(self, command_data):
        try:
            text = command_data.get("text", "")
            if text:
                if text == '\b':
                    self.keyboard.press(Key.backspace)
                    self.keyboard.release(Key.backspace)
                elif text == '\r' or text == '\n':
                    self.keyboard.press(Key.enter)
                    self.keyboard.release(Key.enter)
                elif text == '\t':
                    self.keyboard.press(Key.tab)
                    self.keyboard.release(Key.tab)
                else:
                    self.keyboard.type(text)
        except:
            pass
    
    def stop(self):
        self.is_running = False
        self.is_connected = False
        self.streaming_clients.clear()
        self.connected_clients_list.clear()
        self.sending_screenshots = False
        self.stop_updaters()
        
        DatabaseManager.update_computer_status(self.computer_id, False, self.session_id)
        self.log_message.emit(f"Агент остановлен: computer_id={self.computer_id}")


class RemoteAgentWindow(QMainWindow):
    def __init__(self, computer_data):
        super().__init__()
        self.computer_data = computer_data
        self.agent_thread = None
        self.tray_icon = None
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_system_data)
        self.update_timer.start(1800000)  # 30 минут
        
        # Сохраняем текущую сессию
        if computer_data.get('session_id'):
            DatabaseManager.set_current_session(
                computer_data['computer_id'], 
                computer_data['session_id']
            )
        
        self.init_ui()
        self.load_settings()
        self.update_system_data()
        
        if self.auto_reconnect:
            QTimer.singleShot(1000, self.connect_to_server)
        
        if self.minimize_to_tray:
            self.hide()
            self.create_tray_icon()
        
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    
    def init_ui(self):
        self.setWindowTitle("Remote Access Agent")
        self.setGeometry(300, 300, 550, 450)
        self.setStyleSheet(APP_STYLE)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        header_layout = QHBoxLayout(header_frame)
        
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 12px;")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(40, 40)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                font-size: 20px;
                border-radius: 20px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(self.settings_btn)
        header_layout.setContentsMargins(10, 5, 15, 5)
        
        main_layout.addWidget(header_frame)
        
        info_group = QGroupBox("ИНФОРМАЦИЯ О СИСТЕМЕ")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)
        
        self.computer_label = QLabel()
        self.computer_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff8c42;")
        self.computer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.computer_label)
        
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 8px; padding: 10px;")
        status_layout = QVBoxLayout(status_frame)
        
        self.status_label = QLabel("● Не подключен")
        self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_label)
        
        info_layout.addWidget(status_frame)
        
        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)
        
        log_group = QGroupBox("ЖУРНАЛ СОБЫТИЙ")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ff8c42;
                border-radius: 5px;
                background-color: #fafafa;
            }
        """)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        exit_frame = QFrame()
        exit_layout = QHBoxLayout(exit_frame)
        exit_layout.addStretch()
        
        self.exit_btn = QPushButton("✖ ВЫХОД")
        self.exit_btn.setFixedWidth(120)
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.exit_btn.clicked.connect(self.quit_application)
        exit_layout.addWidget(self.exit_btn)
        
        main_layout.addWidget(exit_frame)
        
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("background-color: #f0f0f0; color: #666666;")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")
        
        self.update_computer_info()
    
    def update_computer_info(self):
        computer_name = self.computer_data['hostname']
        self.computer_label.setText(f"🖥️ {computer_name}")
    
    def update_system_data(self):
        if self.computer_data.get('computer_id'):
            ip = DatabaseManager.get_local_ip()
            DatabaseManager.update_ip_address(self.computer_data['computer_id'], ip)
            DatabaseManager.update_hardware_config(self.computer_data['computer_id'])
    
    def create_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(255, 140, 66))
        icon = QIcon(pixmap)
        
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Remote Access Agent")
        
        tray_menu = QMenu()
        
        show_action = QAction("👁 Показать окно", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        settings_action = QAction("⚙ Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("✖ Выход", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
    
    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()
    
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()
    
    def quit_application(self):
        reply = QMessageBox.question(
            self, 
            "Подтверждение", 
            "Вы уверены, что хотите выйти?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(2000)
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], 
                    False, 
                    self.computer_data.get('session_id')
                )
            QApplication.quit()
    
    def show_about(self):
        QMessageBox.about(
            self,
            "О программе",
            "<h3 style='color: #ff8c42;'>Remote Access Agent</h3>"
            "<p>Версия: 2.0.0</p>"
            "<p>Автоматическая регистрация компьютера в системе</p>"
            "<p>Мониторинг системной активности</p>"
            "<p>© Remote Access System</p>"
        )
    
    def load_settings(self):
        settings = QSettings("RemoteAccess", "Agent")
        self.server = settings.value("server", "ws://localhost:9001")
        self.quality = int(settings.value("quality", 70))
        self.fps = float(settings.value("fps", 20))
        self.auto_reconnect = settings.value("auto_reconnect", True, type=bool)
        self.minimize_to_tray = settings.value("minimize_to_tray", True, type=bool)
    
    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            dialog.save_settings()
            self.load_settings()
            
            if self.agent_thread and self.agent_thread.is_connected:
                interval = 1.0 / self.fps if self.fps > 0 else 0.05
                self.agent_thread.update_settings(interval, self.quality)
                self.log(f"Настройки обновлены: FPS={self.fps}, Качество={self.quality}%")
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
    
    def connect_to_server(self):
        if not self.server.startswith('ws://'):
            QMessageBox.warning(self, "Ошибка", "Сервер должен начинаться с ws://")
            return
        
        self.log(f"Подключение к серверу: {self.server}")
        
        interval = 1.0 / self.fps if self.fps > 0 else 0.05
        
        self.agent_thread = RemoteAgentThread(
            relay_server=self.server,
            computer_data=self.computer_data,
            screenshot_interval=interval,
            quality=self.quality
        )
        
        self.agent_thread.log_message.connect(self.log)
        self.agent_thread.connection_status_changed.connect(self.on_connection_status_changed)
        self.agent_thread.client_connected.connect(self.on_client_connected)
        self.agent_thread.client_disconnected.connect(self.on_client_disconnected)
        self.agent_thread.activity_status.connect(self.update_activity_status)
        
        self.agent_thread.start()
    
    def disconnect_from_server(self):
        if self.agent_thread:
            self.agent_thread.stop()
            self.agent_thread.wait(2000)
            self.agent_thread = None
        self.log("Отключен от сервера")
        self.status_label.setText("● Не подключен")
        self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
    
    def update_activity_status(self, status):
        self.activity_label.setText(f"📊 {status}")
    
    def on_connection_status_changed(self, is_connected, clients_count):
        if is_connected:
            self.status_label.setText("● Подключен к серверу")
            self.status_label.setStyleSheet("font-size: 13px; color: #27ae60; font-weight: bold;")
            self.log("Успешно подключен к серверу")
            self.status_bar.showMessage("Подключен к серверу")
            
            if self.tray_icon:
                self.tray_icon.setToolTip("Remote Access Agent - Подключен")
        else:
            self.status_label.setText("● Не подключен")
            self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
            self.status_bar.showMessage("Отключен от сервера")
            
            if self.tray_icon:
                self.tray_icon.setToolTip("Remote Access Agent - Отключен")
    
    def on_client_connected(self, client_id):
        self.log(f"✅ Клиент подключился: {client_id}")
        self.status_bar.showMessage(f"Клиент {client_id} подключился", 5000)
        
        if self.tray_icon:
            self.tray_icon.showMessage(
                "Новое подключение",
                f"Клиент {client_id} подключился",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def on_client_disconnected(self, client_id):
        self.log(f"❌ Клиент отключился: {client_id}")
    
    def closeEvent(self, event):
        if self.minimize_to_tray and self.tray_icon:
            event.ignore()
            self.hide()
        else:
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(2000)
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], 
                    False, 
                    self.computer_data.get('session_id')
                )
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Remote Access Agent")
    app.setWindowIcon(QIcon())
    
    def on_about_to_quit():
        if hasattr(app, 'window') and app.window:
            if app.window.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    app.window.computer_data['computer_id'], 
                    False, 
                    app.window.computer_data.get('session_id')
                )
    
    app.aboutToQuit.connect(on_about_to_quit)
    
    auth_dialog = AutoAuthDialog()
    if auth_dialog.exec() == QDialog.DialogCode.Accepted:
        window = RemoteAgentWindow(auth_dialog.computer_data)
        app.window = window
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()