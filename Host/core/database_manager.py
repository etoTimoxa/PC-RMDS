"""Управление подключением к базе данных"""

import pymysql
import pymysql.cursors
import hashlib
import re
import socket
import platform
import subprocess
import psutil
from typing import Optional, Dict, Any
from datetime import datetime

from utils.constants import DB_CONFIG, STATUS_ACTIVE, STATUS_DISCONNECTED
from core.hardware_id import HardwareIDGenerator


class DatabaseManager:
    """Класс для работы с базой данных"""
    
    current_session_id: Optional[int] = None
    current_computer_id: Optional[int] = None
    
    @classmethod
    def get_connection(cls):
        """Получить соединение с БД"""
        try:
            # Убеждаемся, что cursorclass установлен правильно
            config = DB_CONFIG.copy()
            if 'cursorclass' not in config:
                config['cursorclass'] = pymysql.cursors.DictCursor
            return pymysql.connect(**config)
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None
    
    @classmethod
    def set_current_session(cls, computer_id: int, session_id: int):
        cls.current_computer_id = computer_id
        cls.current_session_id = session_id
    
    @staticmethod
    def generate_session_token(computer_hostname: str) -> str:
        clean_hostname = re.sub(r'[^a-zA-Z0-9_-]', '_', computer_hostname)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"{clean_hostname}_{timestamp}"
    
    @classmethod
    def create_session(cls, computer_id: int, computer_hostname: str) -> Optional[int]:
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                # Завершаем предыдущие активные сессии
                cursor.execute("""
                    UPDATE session 
                    SET status_id = %s,
                        end_time = NOW()
                    WHERE computer_id = %s AND status_id = %s
                """, (STATUS_DISCONNECTED, computer_id, STATUS_ACTIVE))
                
                session_token = cls.generate_session_token(computer_hostname)
                
                cursor.execute("""
                    INSERT INTO session 
                    (computer_id, session_token, start_time, status_id, json_sent_count, error_count)
                    VALUES (%s, %s, NOW(), %s, 0, 0)
                """, (computer_id, session_token, STATUS_ACTIVE))
                
                session_id = cursor.lastrowid
                connection.commit()
                print(f"✅ Создана сессия: id={session_id}, token={session_token}")
                return session_id
        except Exception as e:
            print(f"Ошибка создания сессии: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_session_activity(cls, session_id: int) -> None:
        connection = cls.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE session 
                    SET last_activity = NOW()
                    WHERE session_id = %s
                """, (session_id,))
                connection.commit()
        except Exception as e:
            print(f"Ошибка обновления активности: {e}")
        finally:
            connection.close()
    
    @classmethod
    def update_session_end(cls, session_id: int, status_id: int = None) -> None:
        if status_id is None:
            status_id = STATUS_DISCONNECTED
            
        connection = cls.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE session 
                    SET status_id = %s,
                        end_time = NOW()
                    WHERE session_id = %s
                """, (status_id, session_id))
                connection.commit()
                print(f"✅ Завершена сессия: id={session_id}, status={status_id}")
        except Exception as e:
            print(f"Ошибка завершения сессии: {e}")
        finally:
            connection.close()
    
    @classmethod
    def update_json_sent_count(cls, session_id: int, count: int) -> None:
        connection = cls.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE session 
                    SET json_sent_count = json_sent_count + %s
                    WHERE session_id = %s
                """, (count, session_id))
                connection.commit()
        except Exception as e:
            print(f"Ошибка обновления счетчика JSON: {e}")
        finally:
            connection.close()
    
    @classmethod
    def update_error_count(cls, session_id: int, count: int) -> None:
        connection = cls.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE session 
                    SET error_count = error_count + %s
                    WHERE session_id = %s
                """, (count, session_id))
                connection.commit()
        except Exception as e:
            print(f"Ошибка обновления счетчика ошибок: {e}")
        finally:
            connection.close()
    
    @classmethod
    def get_or_create_os(cls) -> Optional[int]:
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                os_name = platform.system()
                os_version = platform.release()
                os_build = platform.version() if platform.system() == "Windows" else None
                
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
                        (os_name, os_version, os_build, os_architecture)
                        VALUES (%s, %s, %s, %s)
                    """, (os_name, os_version, os_build, os_arch))
                    os_id = cursor.lastrowid
                    connection.commit()
                    return os_id
        except Exception as e:
            print(f"Ошибка получения/создания OS: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def get_or_create_hardware_config(cls) -> Optional[int]:
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cpu_model = platform.processor() or "Unknown"
                cpu_cores = psutil.cpu_count(logical=True)
                ram_total = round(psutil.virtual_memory().total / (1024**3), 2)
                storage_total = round(psutil.disk_usage('/').total / (1024**3), 2)
                
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
                    SELECT config_id FROM hardware_config 
                    WHERE cpu_model = %s AND cpu_cores = %s 
                    AND ram_total = %s AND storage_total = %s
                """, (cpu_model, cpu_cores, ram_total, storage_total))
                
                config = cursor.fetchone()
                
                if config:
                    return config['config_id']
                else:
                    cursor.execute("""
                        INSERT INTO hardware_config 
                        (cpu_model, cpu_cores, ram_total, storage_total, gpu_model, detected_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                    """, (cpu_model, cpu_cores, ram_total, storage_total, gpu_model))
                    config_id = cursor.lastrowid
                    connection.commit()
                    return config_id
        except Exception as e:
            print(f"Ошибка получения/создания hardware config: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_ip_address(cls, computer_id: int, ip_address: str) -> Optional[int]:
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ip_address 
                    (computer_id, ip_address, detected_at)
                    VALUES (%s, %s, NOW())
                """, (computer_id, ip_address))
                ip_id = cursor.lastrowid
                connection.commit()
                return ip_id
        except Exception as e:
            print(f"Ошибка обновления IP: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def register_computer(cls) -> Optional[Dict[str, Any]]:
        connection = cls.get_connection()
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
                
                # Проверяем существующий компьютер
                cursor.execute("""
                    SELECT c.computer_id, c.hostname, c.mac_address, cred.login, cred.password_hash
                    FROM computer c
                    INNER JOIN credential cred ON c.credential_id = cred.credential_id
                    WHERE c.mac_address = %s
                """, (mac_address,))
                
                existing = cursor.fetchone()
                
                if existing:
                    if existing['password_hash'] == password_hash:
                        cursor.execute("""
                            UPDATE computer SET hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (hostname, existing['computer_id']))
                        connection.commit()
                        
                        ip_address = cls.get_local_ip()
                        cls.update_ip_address(existing['computer_id'], ip_address)
                        session_id = cls.create_session(existing['computer_id'], hostname)
                        
                        cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                        token_data = cursor.fetchone()
                        session_token = token_data['session_token'] if token_data else None
                        
                        return {
                            'computer_id': existing['computer_id'],
                            'hostname': hostname,
                            'mac_address': existing['mac_address'],
                            'login': existing['login'],
                            'password': computer_password,
                            'is_new': False,
                            'session_id': session_id,
                            'session_token': session_token
                        }
                    return None
                
                # Создаем учетные данные
                cursor.execute("""
                    INSERT INTO credential (login, password_hash, is_active, created_at)
                    VALUES (%s, %s, 1, NOW())
                """, (computer_login, password_hash))
                credential_id = cursor.lastrowid
                
                os_id = cls.get_or_create_os()
                hardware_config_id = cls.get_or_create_hardware_config()
                
                cursor.execute("""
                    INSERT INTO computer 
                    (credential_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'client', 1, NOW(), NOW())
                """, (credential_id, os_id, hardware_config_id, hostname, mac_address))
                computer_id = cursor.lastrowid
                connection.commit()
                
                ip_address = cls.get_local_ip()
                cls.update_ip_address(computer_id, ip_address)
                session_id = cls.create_session(computer_id, hostname)
                
                cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                token_data = cursor.fetchone()
                session_token = token_data['session_token'] if token_data else None
                
                HardwareIDGenerator.save_credentials(computer_login, computer_password)
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'login': computer_login,
                    'password': computer_password,
                    'is_new': True,
                    'session_id': session_id,
                    'session_token': session_token
                }
        except Exception as e:
            print(f"Ошибка регистрации компьютера: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def authenticate_computer(cls) -> Optional[Dict[str, Any]]:
        unique_id = HardwareIDGenerator.generate_unique_id()
        computer_login = f"comp_{unique_id[:16]}"
        computer_password = unique_id
        password_hash = hashlib.sha256(computer_password.encode()).hexdigest()
        
        connection = cls.get_connection()
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
                    WHERE cred.login = %s AND cred.password_hash = %s AND cred.is_active = 1
                """, (computer_login, password_hash))
                
                computer_data = cursor.fetchone()
                
                if computer_data:
                    hostname = socket.gethostname()
                    if computer_data['hostname'] != hostname:
                        cursor.execute("""
                            UPDATE computer SET hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (hostname, computer_data['computer_id']))
                        connection.commit()
                    
                    ip_address = cls.get_local_ip()
                    cls.update_ip_address(computer_data['computer_id'], ip_address)
                    session_id = cls.create_session(computer_data['computer_id'], hostname)
                    
                    cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                    token_data = cursor.fetchone()
                    session_token = token_data['session_token'] if token_data else None
                    
                    return {
                        'computer_id': computer_data['computer_id'],
                        'hostname': hostname,
                        'mac_address': computer_data['mac_address'],
                        'login': computer_data['login'],
                        'os_name': computer_data.get('os_name', 'Unknown'),
                        'os_version': computer_data.get('os_version', 'Unknown'),
                        'session_id': session_id,
                        'session_token': session_token,
                        'is_new': False
                    }
                return None
        except Exception as e:
            print(f"Ошибка аутентификации: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_computer_status(cls, computer_id: int, is_online: bool, session_id: int = None) -> None:
        connection = cls.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE computer SET is_online = %s, last_online = NOW()
                    WHERE computer_id = %s
                """, (1 if is_online else 0, computer_id))
                
                if session_id and not is_online:
                    cls.update_session_end(session_id, STATUS_DISCONNECTED)
                connection.commit()
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
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