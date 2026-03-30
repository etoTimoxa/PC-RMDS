import pymysql
import pymysql.cursors
import hashlib
import re
import socket
import platform
import subprocess
import psutil
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import sys
import traceback

from utils.constants import DB_CONFIG, STATUS_ACTIVE, STATUS_DISCONNECTED
from core.hardware_id import HardwareIDGenerator


class DatabaseManager:
    
    current_session_id: Optional[int] = None
    current_computer_id: Optional[int] = None
    
    @classmethod
    def get_connection(cls):
        try:
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
                # Закрываем предыдущие активные сессии
                cursor.execute("""
                    UPDATE session 
                    SET status_id = %s,
                        end_time = NOW()
                    WHERE computer_id = %s AND status_id = %s
                """, (STATUS_DISCONNECTED, computer_id, STATUS_ACTIVE))
                
                session_token = cls.generate_session_token(computer_hostname)
                
                cursor.execute("""
                    INSERT INTO session 
                    (computer_id, session_token, start_time, status_id, json_sent_count, error_count, last_activity)
                    VALUES (%s, %s, NOW(), %s, 0, 0, NOW())
                """, (computer_id, session_token, STATUS_ACTIVE))
                
                session_id = cursor.lastrowid
                connection.commit()
                return session_id
        except Exception as e:
            print(f"Ошибка создания сессии: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_session_activity(cls, session_id: int) -> None:
        """Обновляет время последней активности сессии"""
        if not session_id:
            return
            
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
    def get_motherboard_info_windows(cls) -> Tuple[str, str]:
        """Получение информации о материнской плате и BIOS через WMI (Windows)"""
        motherboard = "Unknown"
        bios_version = "Unknown"
        
        try:
            import wmi
            c = wmi.WMI()
            
            for board in c.Win32_BaseBoard():
                if board.Product:
                    motherboard = board.Product
                elif board.Name:
                    motherboard = board.Name
                break
            
            for bios in c.Win32_BIOS():
                bios_version = bios.Version if bios.Version else "Unknown"
                break
                
        except ImportError:
            print("WMI не установлен. Установите: pip install wmi")
        except Exception as e:
            print(f"Ошибка получения информации WMI: {e}")
        
        return motherboard, bios_version
    
    @classmethod
    def get_motherboard_info_linux(cls) -> Tuple[str, str]:
        """Получение информации о материнской плате в Linux"""
        motherboard = "Unknown"
        bios_version = "Unknown"
        
        try:
            dmi_paths = {
                'motherboard': ['/sys/class/dmi/id/board_name', '/sys/class/dmi/id/product_name'],
                'bios': ['/sys/class/dmi/id/bios_version']
            }
            
            for path in dmi_paths['motherboard']:
                try:
                    with open(path, 'r') as f:
                        motherboard = f.read().strip()
                        if motherboard:
                            break
                except:
                    pass
            
            for path in dmi_paths['bios']:
                try:
                    with open(path, 'r') as f:
                        bios_version = f.read().strip()
                        if bios_version:
                            break
                except:
                    pass
                    
        except Exception as e:
            print(f"Ошибка получения информации DMI: {e}")
        
        return motherboard, bios_version
    
    @classmethod
    def get_motherboard_info(cls) -> Tuple[str, str]:
        """Получение информации о материнской плате и BIOS (кросс-платформенный)"""
        if platform.system() == "Windows":
            return cls.get_motherboard_info_windows()
        elif platform.system() == "Linux":
            return cls.get_motherboard_info_linux()
        else:
            return "Unknown", "Unknown"
    
    @classmethod
    def get_or_create_hardware_config(cls) -> Optional[int]:
        """Получает или создает конфигурацию оборудования"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cpu_model = platform.processor() or "Unknown"
                cpu_cores = psutil.cpu_count(logical=True)
                ram_total = round(psutil.virtual_memory().total / (1024**3), 2)
                storage_total = round(psutil.disk_usage('/').total / (1024**3), 2)
                
                motherboard, bios_version = cls.get_motherboard_info()
                
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
                elif platform.system() == "Linux":
                    try:
                        cmd = "lspci | grep VGA"
                        output = subprocess.check_output(cmd, shell=True).decode()
                        if output:
                            gpu_model = output.split(':')[-1].strip()
                    except:
                        pass
                
                cursor.execute("""
                    SELECT config_id FROM hardware_config 
                    WHERE cpu_model = %s AND cpu_cores = %s 
                    AND ram_total = %s AND storage_total = %s
                    AND motherboard = %s AND bios_version = %s
                """, (cpu_model, cpu_cores, ram_total, storage_total, motherboard, bios_version))
                
                config = cursor.fetchone()
                
                if config:
                    return config['config_id']
                else:
                    cursor.execute("""
                        INSERT INTO hardware_config 
                        (cpu_model, cpu_cores, ram_total, storage_total, gpu_model, 
                         motherboard, bios_version, detected_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (cpu_model, cpu_cores, ram_total, storage_total, gpu_model, 
                          motherboard, bios_version))
                    config_id = cursor.lastrowid
                    connection.commit()
                    print(f"Создана новая конфигурация оборудования с ID: {config_id}")
                    return config_id
                    
        except Exception as e:
            print(f"Ошибка получения/создания hardware config: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def get_network_info_windows(cls) -> Dict[str, str]:
        """Получение сетевой информации через ipconfig (Windows)"""
        network_info = {
            'ip_address': 'Unknown',
            'subnet_mask': 'Unknown',
            'gateway': 'Unknown'
        }
        
        try:
            result = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='cp866')
            output = result.stdout
            
            lines = output.split('\n')
            current_adapter = None
            has_ip = False
            
            for i, line in enumerate(lines):
                if 'Адаптер' in line or 'adapter' in line.lower():
                    current_adapter = line
                    has_ip = False
                
                if current_adapter and ('IPv4-адрес' in line or 'IPv4 Address' in line):
                    parts = line.split(':')
                    if len(parts) > 1:
                        ip = parts[1].strip()
                        if ip and ip != '0.0.0.0' and not ip.startswith('169.254'):
                            network_info['ip_address'] = ip
                            has_ip = True
                
                if has_ip and ('Маска подсети' in line or 'Subnet Mask' in line):
                    parts = line.split(':')
                    if len(parts) > 1:
                        network_info['subnet_mask'] = parts[1].strip()
                
                if has_ip and ('Основной шлюз' in line or 'Default Gateway' in line):
                    parts = line.split(':')
                    if len(parts) > 1:
                        gateway = parts[1].strip()
                        if gateway and gateway != '0.0.0.0':
                            network_info['gateway'] = gateway
                            break
            
            if network_info['ip_address'] == 'Unknown':
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                network_info['ip_address'] = s.getsockname()[0]
                s.close()
                
        except Exception as e:
            print(f"Ошибка получения сетевой информации через ipconfig: {e}")
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            network_info['ip_address'] = s.getsockname()[0]
            s.close()
        
        return network_info
    
    @classmethod
    def get_network_info_linux(cls) -> Dict[str, str]:
        """Получение сетевой информации в Linux"""
        network_info = {
            'ip_address': 'Unknown',
            'subnet_mask': 'Unknown',
            'gateway': 'Unknown'
        }
        
        try:
            result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                   capture_output=True, text=True)
            route = result.stdout
            
            if route:
                parts = route.split()
                if 'via' in parts:
                    idx = parts.index('via')
                    if idx + 1 < len(parts):
                        network_info['gateway'] = parts[idx + 1]
                
                if 'dev' in parts:
                    idx = parts.index('dev')
                    if idx + 1 < len(parts):
                        interface = parts[idx + 1]
                        
                        result = subprocess.run(['ip', 'addr', 'show', interface], 
                                               capture_output=True, text=True)
                        addr_output = result.stdout
                        
                        for line in addr_output.split('\n'):
                            if 'inet ' in line:
                                parts = line.strip().split()
                                if len(parts) > 1:
                                    ip_with_mask = parts[1]
                                    if '/' in ip_with_mask:
                                        ip, mask_bits = ip_with_mask.split('/')
                                        network_info['ip_address'] = ip
                                        network_info['subnet_mask'] = cls.cidr_to_netmask(int(mask_bits))
                                    break
            
            if network_info['ip_address'] == 'Unknown':
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                network_info['ip_address'] = s.getsockname()[0]
                s.close()
                
        except Exception as e:
            print(f"Ошибка получения сетевой информации в Linux: {e}")
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            network_info['ip_address'] = s.getsockname()[0]
            s.close()
        
        return network_info
    
    @staticmethod
    def cidr_to_netmask(cidr: int) -> str:
        """Преобразование CIDR в маску подсети"""
        mask = (0xffffffff >> (32 - cidr)) << (32 - cidr)
        return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
    
    @classmethod
    def get_network_info(cls) -> Dict[str, str]:
        """Получение информации о сети (кросс-платформенный)"""
        if platform.system() == "Windows":
            return cls.get_network_info_windows()
        elif platform.system() == "Linux":
            return cls.get_network_info_linux()
        else:
            network_info = {
                'ip_address': 'Unknown',
                'subnet_mask': 'Unknown',
                'gateway': 'Unknown'
            }
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                network_info['ip_address'] = s.getsockname()[0]
                s.close()
            except:
                pass
            return network_info
    
    @classmethod
    def get_last_ip_info(cls, computer_id: int) -> Optional[Dict[str, str]]:
        """Получение последней записи IP для компьютера"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT ip_address, subnet_mask, gateway 
                    FROM ip_address 
                    WHERE computer_id = %s 
                    ORDER BY detected_at DESC 
                    LIMIT 1
                """, (computer_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'ip_address': result.get('ip_address', 'Unknown'),
                        'subnet_mask': result.get('subnet_mask', 'Unknown'),
                        'gateway': result.get('gateway', 'Unknown')
                    }
                return None
        except Exception as e:
            print(f"Ошибка получения последнего IP: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_ip_address(cls, computer_id: int, network_info: Dict[str, str]) -> Optional[int]:
        """Обновляет IP-адрес только если он изменился"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            last_ip_info = cls.get_last_ip_info(computer_id)
            
            if (last_ip_info and 
                last_ip_info['ip_address'] == network_info['ip_address'] and
                last_ip_info['subnet_mask'] == network_info['subnet_mask'] and
                last_ip_info['gateway'] == network_info['gateway']):
                return None
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ip_address 
                    (computer_id, ip_address, subnet_mask, gateway, detected_at)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (computer_id, 
                      network_info['ip_address'], 
                      network_info['subnet_mask'], 
                      network_info['gateway']))
                ip_id = cursor.lastrowid
                connection.commit()
                return ip_id
        except Exception as e:
            print(f"Ошибка обновления IP: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def get_computer_by_mac(cls, mac_address: str) -> Optional[Dict[str, Any]]:
        """Получение компьютера по MAC-адресу"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        c.computer_id, c.hostname, c.mac_address, c.hardware_config_id,
                        cred.credential_id, cred.login,
                        os.os_name, os.os_version
                    FROM credential cred
                    INNER JOIN computer c ON c.credential_id = cred.credential_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    WHERE c.mac_address = %s AND cred.is_active = 1
                """, (mac_address,))
                return cursor.fetchone()
        except Exception as e:
            print(f"Ошибка получения компьютера по MAC: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_computer_hardware_config(cls, computer_id: int, hardware_config_id: int) -> bool:
        """Обновляет конфигурацию оборудования компьютера"""
        connection = cls.get_connection()
        if not connection:
            return False
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE computer 
                    SET hardware_config_id = %s
                    WHERE computer_id = %s
                """, (hardware_config_id, computer_id))
                connection.commit()
                return True
        except Exception as e:
            print(f"Ошибка обновления hardware_config: {e}")
            return False
        finally:
            connection.close()
    
    @classmethod
    def authenticate_computer(cls) -> Optional[Dict[str, Any]]:
        """Аутентификация компьютера по железу (автоматическая)"""
        unique_id = HardwareIDGenerator.generate_unique_id()
        computer_login = f"comp_{unique_id[:16]}"
        computer_password = unique_id
        password_hash = hashlib.sha256(computer_password.encode()).hexdigest()
        
        mac_address = HardwareIDGenerator.get_mac_address()
        
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                # Ищем компьютер по MAC-адресу
                computer_by_mac = cls.get_computer_by_mac(mac_address)
                
                if computer_by_mac:
                    # Компьютер найден по MAC, проверяем пароль
                    cursor.execute("""
                        SELECT password_hash FROM credential 
                        WHERE credential_id = %s
                    """, (computer_by_mac['credential_id'],))
                    cred_data = cursor.fetchone()
                    
                    if cred_data and cred_data['password_hash'] == password_hash:
                        # Пароль совпадает, авторизуем
                        hostname = socket.gethostname()
                        
                        # Обновляем hostname
                        if computer_by_mac['hostname'] != hostname:
                            cursor.execute("""
                                UPDATE computer SET hostname = %s, last_online = NOW()
                                WHERE computer_id = %s
                            """, (hostname, computer_by_mac['computer_id']))
                            connection.commit()
                            computer_by_mac['hostname'] = hostname
                        
                        # Обновляем конфигурацию железа
                        hardware_config_id = cls.get_or_create_hardware_config()
                        if hardware_config_id and computer_by_mac.get('hardware_config_id') != hardware_config_id:
                            cls.update_computer_hardware_config(computer_by_mac['computer_id'], hardware_config_id)
                            computer_by_mac['hardware_config_id'] = hardware_config_id
                        
                        # Обновляем IP
                        network_info = cls.get_network_info()
                        cls.update_ip_address(computer_by_mac['computer_id'], network_info)
                        
                        # Создаем сессию
                        session_id = cls.create_session(computer_by_mac['computer_id'], hostname)
                        
                        cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                        token_data = cursor.fetchone()
                        session_token = token_data['session_token'] if token_data else None
                        
                        return {
                            'computer_id': computer_by_mac['computer_id'],
                            'hostname': hostname,
                            'mac_address': computer_by_mac['mac_address'],
                            'login': computer_by_mac['login'],
                            'password': computer_password,
                            'os_name': computer_by_mac.get('os_name', 'Unknown'),
                            'os_version': computer_by_mac.get('os_version', 'Unknown'),
                            'session_id': session_id,
                            'session_token': session_token,
                            'is_new': False
                        }
                    else:
                        # Пароль не совпадает - компьютер с таким MAC но другой пароль
                        return None
                
                # Компьютер не найден по MAC
                return None
                
        except Exception as e:
            print(f"Ошибка аутентификации: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def authenticate_by_credentials(cls, login: str, password: str) -> Optional[Dict[str, Any]]:
        """Аутентификация по логину и паролю (ручной вход)"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        c.computer_id, c.hostname, c.mac_address, c.hardware_config_id,
                        cred.credential_id, cred.login,
                        os.os_name, os.os_version
                    FROM credential cred
                    INNER JOIN computer c ON c.credential_id = cred.credential_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    WHERE cred.login = %s AND cred.password_hash = %s AND cred.is_active = 1
                """, (login, password_hash))
                
                computer_data = cursor.fetchone()
                
                if computer_data:
                    hostname = socket.gethostname()
                    
                    # Обновляем hostname если изменился
                    if computer_data['hostname'] != hostname:
                        cursor.execute("""
                            UPDATE computer SET hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (hostname, computer_data['computer_id']))
                        connection.commit()
                        computer_data['hostname'] = hostname
                    
                    # Обновляем конфигурацию железа
                    hardware_config_id = cls.get_or_create_hardware_config()
                    if hardware_config_id and computer_data.get('hardware_config_id') != hardware_config_id:
                        cls.update_computer_hardware_config(computer_data['computer_id'], hardware_config_id)
                        computer_data['hardware_config_id'] = hardware_config_id
                    
                    # Обновляем IP
                    network_info = cls.get_network_info()
                    cls.update_ip_address(computer_data['computer_id'], network_info)
                    
                    # Создаем сессию
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
            print(f"Ошибка аутентификации по логину: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def register_computer(cls) -> Optional[Dict[str, Any]]:
        """Регистрация нового компьютера"""
        print("=== НАЧАЛО РЕГИСТРАЦИИ КОМПЬЮТЕРА ===")
        
        connection = cls.get_connection()
        if not connection:
            print("ОШИБКА: Нет подключения к БД")
            return None
        
        try:
            with connection.cursor() as cursor:
                hostname = socket.gethostname()
                mac_address = HardwareIDGenerator.get_mac_address()
                unique_hardware_id = HardwareIDGenerator.generate_unique_id()
                
                computer_login = f"comp_{unique_hardware_id[:16]}"
                computer_password = unique_hardware_id
                password_hash = hashlib.sha256(computer_password.encode()).hexdigest()
                
                print(f"Хостнейм: {hostname}")
                print(f"MAC: {mac_address}")
                print(f"Логин: {computer_login}")
                print(f"Пароль: {computer_password}")
                
                # Проверяем, не зарегистрирован ли уже компьютер с таким MAC
                cursor.execute("""
                    SELECT c.computer_id, c.hostname, c.mac_address, cred.login, cred.password_hash
                    FROM computer c
                    INNER JOIN credential cred ON c.credential_id = cred.credential_id
                    WHERE c.mac_address = %s
                """, (mac_address,))
                
                existing = cursor.fetchone()
                
                if existing:
                    print(f"Компьютер уже существует с ID: {existing['computer_id']}")
                    if existing['password_hash'] == password_hash:
                        print("Пароль совпадает, обновляем данные")
                        cursor.execute("""
                            UPDATE computer SET hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (hostname, existing['computer_id']))
                        connection.commit()
                        
                        hardware_config_id = cls.get_or_create_hardware_config()
                        if hardware_config_id:
                            cls.update_computer_hardware_config(existing['computer_id'], hardware_config_id)
                        
                        network_info = cls.get_network_info()
                        cls.update_ip_address(existing['computer_id'], network_info)
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
                    else:
                        print("Пароль не совпадает")
                        return None
                
                # Создаем новый компьютер
                print("Создаем новую запись в credential...")
                cursor.execute("""
                    INSERT INTO credential (login, password_hash, is_active, created_at)
                    VALUES (%s, %s, 1, NOW())
                """, (computer_login, password_hash))
                credential_id = cursor.lastrowid
                print(f"Credential ID: {credential_id}")
                
                os_id = cls.get_or_create_os()
                print(f"OS ID: {os_id}")
                
                hardware_config_id = cls.get_or_create_hardware_config()
                print(f"Hardware Config ID: {hardware_config_id}")
                
                if hardware_config_id is None:
                    print("ОШИБКА: не удалось создать hardware_config")
                    return None
                
                print("Создаем запись в computer...")
                cursor.execute("""
                    INSERT INTO computer 
                    (credential_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'client', 1, NOW(), NOW())
                """, (credential_id, os_id, hardware_config_id, hostname, mac_address))
                computer_id = cursor.lastrowid
                connection.commit()
                
                print(f"Создан новый компьютер с ID: {computer_id}")
                
                network_info = cls.get_network_info()
                cls.update_ip_address(computer_id, network_info)
                
                session_id = cls.create_session(computer_id, hostname)
                print(f"Создана сессия ID: {session_id}")
                
                cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                token_data = cursor.fetchone()
                session_token = token_data['session_token'] if token_data else None
                
                print("=== РЕГИСТРАЦИЯ УСПЕШНО ЗАВЕРШЕНА ===")
                
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
            print(f"ОШИБКА регистрации: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def update_computer_status(cls, computer_id: int, is_online: bool, session_id: int = None) -> None:
        """Обновление статуса компьютера"""
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