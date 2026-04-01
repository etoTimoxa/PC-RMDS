import pymysql
import pymysql.cursors
import hashlib
import json
import re
import socket
import platform
import subprocess
import psutil
from typing import Optional, Dict, Any, Tuple, List
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
    def ensure_status_exists(cls, status_id: int, status_name: str) -> bool:
        """Гарантирует существование статуса в базе данных"""
        connection = cls.get_connection()
        if not connection:
            return False
        
        try:
            with connection.cursor() as cursor:
                # Проверяем, существует ли статус
                cursor.execute("""
                    SELECT status_id FROM status WHERE status_id = %s
                """, (status_id,))
                
                if not cursor.fetchone():
                    # Создаем статус если не существует
                    cursor.execute("""
                        INSERT INTO status (status_id, status_name, status_type, description)
                        VALUES (%s, %s, 'session', %s)
                    """, (status_id, status_name, f"Статус {status_name}"))
                    connection.commit()
                    print(f"Создан статус {status_name} с ID {status_id}")
                
                return True
        except Exception as e:
            print(f"Ошибка проверки/создания статуса: {e}")
            return False
        finally:
            connection.close()
    
    @classmethod
    def create_session(cls, computer_id: int, computer_hostname: str) -> Optional[int]:
        # Сначала гарантируем существование необходимых статусов
        cls.ensure_status_exists(STATUS_ACTIVE, "active")
        cls.ensure_status_exists(STATUS_DISCONNECTED, "disconnected")
        
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                # Проверяем что статусы существуют
                cursor.execute("SELECT status_id FROM status WHERE status_id IN (%s, %s)", 
                             (STATUS_ACTIVE, STATUS_DISCONNECTED))
                existing_statuses = cursor.fetchall()
                if len(existing_statuses) < 2:
                    print(f"Ошибка: не все статусы существуют. Найдено: {len(existing_statuses)}")
                    return None
                
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
    def get_or_create_os_family(cls, family_name: str, description: str = None) -> Optional[int]:
        """Получает или создает семейство ОС"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT family_id FROM os_family WHERE family_name = %s
                """, (family_name,))
                
                result = cursor.fetchone()
                if result:
                    return result['family_id']
                
                cursor.execute("""
                    INSERT INTO os_family (family_name, description)
                    VALUES (%s, %s)
                """, (family_name, description))
                family_id = cursor.lastrowid
                connection.commit()
                return family_id
        except Exception as e:
            print(f"Ошибка получения/создания семейства ОС: {e}")
            return None
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
                
                # Определяем семейство ОС
                os_family_name = os_name  # Windows, Linux, macOS
                family_id = cls.get_or_create_os_family(os_family_name, f"Семейство {os_family_name}")
                
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
                        (family_id, os_name, os_version, os_build, os_architecture)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (family_id, os_name, os_version, os_build, os_arch))
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
    def add_ip_record(cls, computer_id: int, network_info: Dict[str, str]) -> Optional[int]:
        """Всегда добавляет новую запись IP-адреса"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
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
                print(f"Добавлена запись IP: {network_info['ip_address']} для компьютера {computer_id}")
                return ip_id
        except Exception as e:
            print(f"Ошибка добавления IP: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def get_computer_by_mac(cls, mac_address: str) -> Optional[Dict[str, Any]]:
        """Получение компьютера по MAC-адресу (новая схема с user таблицей)"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        c.computer_id, c.hostname, c.mac_address, c.hardware_config_id,
                        c.computer_type, c.user_id,
                        u.user_id as uid, u.login, u.role_id,
                        os.os_name, os.os_version
                    FROM computer c
                    LEFT JOIN user u ON c.user_id = u.user_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    WHERE c.mac_address = %s
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
    def get_user_by_login(cls, login: str) -> Optional[Dict[str, Any]]:
        """Получение пользователя по логину"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, login, password_hash, full_name, role_id, is_active
                    FROM user WHERE login = %s
                """, (login,))
                return cursor.fetchone()
        except Exception as e:
            print(f"Ошибка получения пользователя: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def get_role_id(cls, role_name: str) -> Optional[int]:
        """Получение ID роли по названию"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT role_id FROM role WHERE role_name = %s
                """, (role_name,))
                result = cursor.fetchone()
                return result['role_id'] if result else None
        except Exception as e:
            print(f"Ошибка получения роли: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def create_user(cls, login: str, password: str, full_name: str = None, role_name: str = 'client') -> Optional[int]:
        """Создание нового пользователя"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            role_id = cls.get_role_id(role_name)
            
            if role_id is None:
                print(f"Роль '{role_name}' не найдена")
                return None
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user (login, password_hash, full_name, role_id, is_active, created_at)
                    VALUES (%s, %s, %s, %s, 1, NOW())
                """, (login, password_hash, full_name or login, role_id))
                user_id = cursor.lastrowid
                connection.commit()
                return user_id
        except Exception as e:
            print(f"Ошибка создания пользователя: {e}")
            return None
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
                    # Компьютер найден по MAC, проверяем пользователя
                    user_id = computer_by_mac.get('user_id')
                    
                    if user_id:
                        # Проверяем пароль пользователя
                        cursor.execute("""
                            SELECT password_hash FROM user WHERE user_id = %s
                        """, (user_id,))
                        user_data = cursor.fetchone()
                        
                        if user_data and user_data['password_hash'] == password_hash:
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
                                'user_id': user_id,
                                'role_id': computer_by_mac.get('role_id'),
                                'computer_type': computer_by_mac.get('computer_type', 'client'),
                                'os_name': computer_by_mac.get('os_name', 'Unknown'),
                                'os_version': computer_by_mac.get('os_version', 'Unknown'),
                                'session_id': session_id,
                                'session_token': session_token,
                                'is_new': False
                            }
                        else:
                            # Пароль не совпадает
                            return None
                    else:
                        # Компьютер без привязки к пользователю
                        return None
                else:
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
                # Ищем пользователя по логину и сравниваем хэш пароля
                cursor.execute("""
                    SELECT user_id, login, password_hash, full_name, role_id, is_active
                    FROM user WHERE login = %s AND password_hash = %s
                """, (login, password_hash))
                
                user_data = cursor.fetchone()
                
                if user_data:
                    # Проверяем, активен ли пользователь
                    if not user_data.get('is_active', 0):
                        print("Пользователь не активен")
                        return None
                    
                    # Проверяем, есть ли компьютеры у этого пользователя
                    cursor.execute("""
                        SELECT computer_id, hostname, mac_address, hardware_config_id, computer_type
                        FROM computer WHERE user_id = %s LIMIT 1
                    """, (user_data['user_id'],))
                    
                    computer_data = cursor.fetchone()
                    
                    # Для админа (role_id = 2 или 3) - без компьютера
                    role_id = user_data.get('role_id')
                    is_admin = role_id in (2, 3) or str(role_id) in ('2', '3')
                    
                    if computer_data:
                        hostname = socket.gethostname()
                        computer_id = computer_data['computer_id']
                        
                        # Обновляем hostname если изменился
                        if computer_data['hostname'] != hostname:
                            cursor.execute("""
                                UPDATE computer SET hostname = %s, last_online = NOW()
                                WHERE computer_id = %s
                            """, (hostname, computer_id))
                            connection.commit()
                        
                        # Обновляем конфигурацию железа
                        hardware_config_id = cls.get_or_create_hardware_config()
                        if hardware_config_id and computer_data.get('hardware_config_id') != hardware_config_id:
                            cls.update_computer_hardware_config(computer_id, hardware_config_id)
                        
                        # Обновляем IP
                        network_info = cls.get_network_info()
                        cls.update_ip_address(computer_id, network_info)
                        
                        # Создаем сессию
                        session_id = cls.create_session(computer_id, hostname)
                        
                        cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                        token_data = cursor.fetchone()
                        session_token = token_data['session_token'] if token_data else None
                        
                        # Обновляем last_login
                        cursor.execute("UPDATE user SET last_login = NOW() WHERE user_id = %s", (user_data['user_id'],))
                        connection.commit()
                        
                        return {
                            'computer_id': computer_id,
                            'hostname': hostname,
                            'mac_address': computer_data['mac_address'],
                            'login': user_data['login'],
                            'user_id': user_data['user_id'],
                            'role_id': user_data['role_id'],
                            'computer_type': computer_data.get('computer_type', 'client'),
                            'session_id': session_id,
                            'session_token': session_token,
                            'is_new': False
                        }
                    elif is_admin:
                        # Админ без компьютера - возвращаем успешную авторизацию
                        cursor.execute("UPDATE user SET last_login = NOW() WHERE user_id = %s", (user_data['user_id'],))
                        connection.commit()
                        
                        return {
                            'computer_id': None,
                            'hostname': socket.gethostname(),
                            'mac_address': None,
                            'login': user_data['login'],
                            'user_id': user_data['user_id'],
                            'role_id': user_data['role_id'],
                            'computer_type': 'admin',
                            'session_id': None,
                            'session_token': None,
                            'is_new': False,
                            'no_computer': True
                        }
                    
                    return None
                return None
        except Exception as e:
            print(f"Ошибка аутентификации по логину: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def register_only_hardware(cls) -> Optional[Dict[str, Any]]:
        """Регистрация железа БЕЗ создания пользователя - только запись в computer"""
        print("=== РЕГИСТРАЦИЯ ЖЕЛЕЗА (БЕЗ ПОЛЬЗОВАТЕЛЯ) ===")
        
        connection = cls.get_connection()
        if not connection:
            print("ОШИБКА: Нет подключения к БД")
            return None
        
        try:
            with connection.cursor() as cursor:
                hostname = socket.gethostname()
                mac_address = HardwareIDGenerator.get_mac_address()
                
                print(f"Хостнейм: {hostname}")
                print(f"MAC: {mac_address}")
                
                # Проверяем, не зарегистрирован ли уже компьютер с таким MAC
                cursor.execute("""
                    SELECT computer_id, hostname, user_id, hardware_config_id
                    FROM computer WHERE mac_address = %s
                """, (mac_address,))
                
                existing = cursor.fetchone()
                
                if existing:
                    print(f"Компьютер уже существует с ID: {existing['computer_id']}")
                    
                    # Обновляем данные
                    cursor.execute("""
                        UPDATE computer SET hostname = %s, last_online = NOW()
                        WHERE computer_id = %s
                    """, (hostname, existing['computer_id']))
                    connection.commit()
                    
                    hardware_config_id = cls.get_or_create_hardware_config()
                    if hardware_config_id and existing.get('hardware_config_id') != hardware_config_id:
                        cls.update_computer_hardware_config(existing['computer_id'], hardware_config_id)
                    
                    network_info = cls.get_network_info()
                    cls.update_ip_address(existing['computer_id'], network_info)
                    
                    # Проверяем, изменилось ли железо
                    hardware_changed = existing.get('hardware_config_id') != hardware_config_id
                    
                    return {
                        'computer_id': existing['computer_id'],
                        'hostname': hostname,
                        'mac_address': mac_address,
                        'user_id': existing.get('user_id'),
                        'hardware_config_id': hardware_config_id,
                        'hardware_changed': hardware_changed,
                        'is_new': False
                    }
                
                # Создаем новый компьютер БЕЗ пользователя
                print("Создаем новую запись о компьютере...")
                
                os_id = cls.get_or_create_os()
                hardware_config_id = cls.get_or_create_hardware_config()
                
                if hardware_config_id is None:
                    print("ОШИБКА: не удалось создать hardware_config")
                    return None
                
                print("Создаем запись в computer...")
                cursor.execute("""
                    INSERT INTO computer 
                    (user_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (NULL, %s, %s, %s, %s, 'client', 1, NOW(), NOW())
                """, (os_id, hardware_config_id, hostname, mac_address))
                computer_id = cursor.lastrowid
                connection.commit()
                
                print(f"Создан новый компьютер с ID: {computer_id}")
                
                network_info = cls.get_network_info()
                cls.update_ip_address(computer_id, network_info)
                
                print("=== РЕГИСТРАЦИЯ ЖЕЛЕЗА УСПЕШНО ЗАВЕРШЕНА ===")
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'user_id': None,
                    'hardware_config_id': hardware_config_id,
                    'hardware_changed': False,
                    'is_new': True
                }
        except Exception as e:
            print(f"ОШИБКА регистрации: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def authenticate_and_bind_admin(cls, login: str, password: str, computer_id: int) -> Optional[Dict[str, Any]]:
        """Аутентификация админа и привязка компьютера к админу"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                # Ищем пользователя по логину и паролю
                cursor.execute("""
                    SELECT user_id, login, password_hash, full_name, role_id, is_active
                    FROM user WHERE login = %s AND password_hash = %s
                """, (login, password_hash))
                
                user_data = cursor.fetchone()
                
                if not user_data:
                    print("Пользователь не найден или неверный пароль")
                    return None
                
                # Проверяем активность
                if not user_data.get('is_active', 0):
                    print("Пользователь не активен")
                    return None
                
                # Проверяем роль (должен быть админ)
                role_id = user_data.get('role_id')
                is_admin = role_id in (2, 3) or str(role_id) in ('2', '3')
                
                if not is_admin:
                    print("Пользователь не является администратором")
                    return None
                
                # Привязываем компьютер к админу
                cursor.execute("""
                    UPDATE computer SET user_id = %s, computer_type = 'admin', last_online = NOW()
                    WHERE computer_id = %s
                """, (user_data['user_id'], computer_id))
                connection.commit()
                
                # Обновляем конфигурацию железа
                hardware_config_id = cls.get_or_create_hardware_config()
                if hardware_config_id:
                    cls.update_computer_hardware_config(computer_id, hardware_config_id)
                
                # Обновляем IP только если изменился
                network_info = cls.get_network_info()
                ip_id = cls.update_ip_address(computer_id, network_info)
                if ip_id:
                    print(f"IP адрес изменен, записан с ID: {ip_id}")
                
                # Обновляем last_login
                cursor.execute("UPDATE user SET last_login = NOW() WHERE user_id = %s", (user_data['user_id'],))
                connection.commit()
                
                print(f"Компьютер {computer_id} привязан к админу {login}")
                
                return {
                    'computer_id': computer_id,
                    'hostname': socket.gethostname(),
                    'mac_address': HardwareIDGenerator.get_mac_address(),
                    'login': user_data['login'],
                    'user_id': user_data['user_id'],
                    'role_id': user_data['role_id'],
                    'computer_type': 'admin',
                    'session_id': None,  # Админ не создает сессию клиента
                    'session_token': None,
                    'is_admin': True,
                    'is_new': False
                }
        except Exception as e:
            print(f"Ошибка аутентификации админа: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def authenticate_or_create_client(cls, login: str, password: str, computer_id: int) -> Optional[Dict[str, Any]]:
        """Аутентификация клиента или создание нового аккаунта"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                # Ищем пользователя по логину и паролю
                cursor.execute("""
                    SELECT user_id, login, password_hash, full_name, role_id, is_active
                    FROM user WHERE login = %s AND password_hash = %s
                """, (login, password_hash))
                
                user_data = cursor.fetchone()
                
                if user_data:
                    # Пользователь найден - проверяем активность
                    if not user_data.get('is_active', 0):
                        print("Пользователь не активен")
                        return None
                    
                    # Проверяем роль (не должен быть админом)
                    role_id = user_data.get('role_id')
                    is_admin = role_id in (2, 3) or str(role_id) in ('2', '3')
                    
                    if is_admin:
                        print("Нельзя использовать аккаунт админа для клиента")
                        return None
                    
                    # Привязываем компьютер к пользователю
                    cursor.execute("""
                        UPDATE computer SET user_id = %s, computer_type = 'client', last_online = NOW()
                        WHERE computer_id = %s
                    """, (user_data['user_id'], computer_id))
                    connection.commit()
                    
                    # Обновляем конфигурацию железа
                    hardware_config_id = cls.get_or_create_hardware_config()
                    if hardware_config_id:
                        cls.update_computer_hardware_config(computer_id, hardware_config_id)
                    
                    # Обновляем IP только если изменился
                    network_info = cls.get_network_info()
                    cls.update_ip_address(computer_id, network_info)
                    
                    # Создаем сессию
                    hostname = socket.gethostname()
                    session_id = cls.create_session(computer_id, hostname)
                    
                    cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                    token_data = cursor.fetchone()
                    session_token = token_data['session_token'] if token_data else None
                    
                    # Обновляем last_login
                    cursor.execute("UPDATE user SET last_login = NOW() WHERE user_id = %s", (user_data['user_id'],))
                    connection.commit()
                    
                    print(f"Пользователь {login} привязан к компьютеру {computer_id}")
                    
                    return {
                        'computer_id': computer_id,
                        'hostname': hostname,
                        'mac_address': HardwareIDGenerator.get_mac_address(),
                        'login': user_data['login'],
                        'password': password,  # Возвращаем原始ный пароль для сохранения
                        'user_id': user_data['user_id'],
                        'role_id': user_data['role_id'],
                        'computer_type': 'client',
                        'session_id': session_id,
                        'session_token': session_token,
                        'is_admin': False,
                        'is_new': False
                    }
                else:
                    # Пользователь не найден - создаем нового клиента
                    print(f"Создаем новый аккаунт клиента: {login}")
                    
                    user_id = cls.create_user(login, password, login, 'client')
                    
                    if user_id is None:
                        print("Не удалось создать пользователя")
                        return None
                    
                    # Привязываем пользователя к компьютеру
                    cursor.execute("""
                        UPDATE computer SET user_id = %s, computer_type = 'client', last_online = NOW()
                        WHERE computer_id = %s
                    """, (user_id, computer_id))
                    connection.commit()
                    
                    # Обновляем конфигурацию железа
                    hardware_config_id = cls.get_or_create_hardware_config()
                    if hardware_config_id:
                        cls.update_computer_hardware_config(computer_id, hardware_config_id)
                    
                    # Обновляем IP только если изменился
                    network_info = cls.get_network_info()
                    cls.update_ip_address(computer_id, network_info)
                    
                    # Создаем сессию
                    hostname = socket.gethostname()
                    session_id = cls.create_session(computer_id, hostname)
                    
                    cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                    token_data = cursor.fetchone()
                    session_token = token_data['session_token'] if token_data else None
                    
                    print(f"Создан новый клиент {login} и привязан к компьютеру {computer_id}")
                    
                    return {
                        'computer_id': computer_id,
                        'hostname': hostname,
                        'mac_address': HardwareIDGenerator.get_mac_address(),
                        'login': login,
                        'password': password,
                        'user_id': user_id,
                        'role_id': 1,  # client
                        'computer_type': 'client',
                        'session_id': session_id,
                        'session_token': session_token,
                        'is_admin': False,
                        'is_new': True
                    }
        except Exception as e:
            print(f"Ошибка аутентификации/создания клиента: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def register_hardware(cls) -> Optional[Dict[str, Any]]:
        """Регистрация железа с автоматическим созданием временного пользователя"""
        print("=== НАЧАЛО РЕГИСТРАЦИИ ЖЕЛЕЗА ===")
        
        connection = cls.get_connection()
        if not connection:
            print("ОШИБКА: Нет подключения к БД")
            return None
        
        try:
            with connection.cursor() as cursor:
                hostname = socket.gethostname()
                mac_address = HardwareIDGenerator.get_mac_address()
                unique_hardware_id = HardwareIDGenerator.generate_unique_id()
                
                computer_password = unique_hardware_id
                password_hash = hashlib.sha256(computer_password.encode()).hexdigest()
                
                print(f"Хостнейм: {hostname}")
                print(f"MAC: {mac_address}")
                print(f"Пароль железа: {computer_password}")
                
                # Проверяем, не зарегистрирован ли уже компьютер с таким MAC
                cursor.execute("""
                    SELECT computer_id, hostname, user_id, hardware_config_id
                    FROM computer WHERE mac_address = %s
                """, (mac_address,))
                
                existing = cursor.fetchone()
                
                if existing:
                    print(f"Компьютер уже существует с ID: {existing['computer_id']}")
                    user_id = existing['user_id']
                    
                    if user_id:
                        print(f"Компьютер привязан к пользователю ID: {user_id}")
                        # Проверяем пароль
                        cursor.execute("""
                            SELECT password_hash FROM user WHERE user_id = %s
                        """, (user_id,))
                        user_data = cursor.fetchone()
                        
                        if user_data and user_data['password_hash'] == password_hash:
                            print("Пароль совпадает, обновляем данные")
                            cursor.execute("""
                                UPDATE computer SET hostname = %s, last_online = NOW()
                                WHERE computer_id = %s
                            """, (hostname, existing['computer_id']))
                            connection.commit()
                            
                            hardware_config_id = cls.get_or_create_hardware_config()
                            if hardware_config_id and existing.get('hardware_config_id') != hardware_config_id:
                                cls.update_computer_hardware_config(existing['computer_id'], hardware_config_id)
                            
                            network_info = cls.get_network_info()
                            cls.update_ip_address(existing['computer_id'], network_info)
                            session_id = cls.create_session(existing['computer_id'], hostname)
                            
                            cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                            token_data = cursor.fetchone()
                            session_token = token_data['session_token'] if token_data else None
                            
                            # Получаем данные пользователя
                            cursor.execute("""
                                SELECT login, role_id FROM user WHERE user_id = %s
                            """, (user_id,))
                            user_info = cursor.fetchone()
                            
                            return {
                                'computer_id': existing['computer_id'],
                                'hostname': hostname,
                                'mac_address': mac_address,
                                'login': user_info['login'],
                                'password': computer_password,
                                'user_id': user_id,
                                'role_id': user_info['role_id'],
                                'is_new': False,
                                'session_id': session_id,
                                'session_token': session_token,
                                'hardware_changed': existing.get('hardware_config_id') != hardware_config_id
                            }
                        else:
                            print("Пароль не совпадает - железо изменилось")
                            return {
                                'computer_id': existing['computer_id'],
                                'hostname': hostname,
                                'mac_address': mac_address,
                                'password': computer_password,
                                'is_new': False,
                                'hardware_changed': True,
                                'needs_auth': True
                            }
                    else:
                        # Компьютер без пользователя (старая схема) - нужно создать пользователя
                        print("Компьютер без пользователя, создаем временного пользователя...")
                        
                        # Создаем временного пользователя
                        temp_login = f"temp_{mac_address.replace(':', '')[:12]}"
                        temp_user_id = cls.create_user(temp_login, computer_password, temp_login, 'client')
                        
                        if temp_user_id is None:
                            print("Не удалось создать временного пользователя")
                            return None
                        
                        # Привязываем пользователя к компьютеру
                        cursor.execute("""
                            UPDATE computer SET user_id = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (temp_user_id, existing['computer_id']))
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
                            'mac_address': mac_address,
                            'login': temp_login,
                            'password': computer_password,
                            'user_id': temp_user_id,
                            'role_id': 1,  # client
                            'is_new': False,
                            'session_id': session_id,
                            'session_token': session_token,
                            'needs_auth': False  # уже авторизован через временного пользователя
                        }
                
                # Создаем новый компьютер с временным пользователем
                print("Создаем новую запись о компьютере...")
                
                os_id = cls.get_or_create_os()
                print(f"OS ID: {os_id}")
                
                hardware_config_id = cls.get_or_create_hardware_config()
                print(f"Hardware Config ID: {hardware_config_id}")
                
                if hardware_config_id is None:
                    print("ОШИБКА: не удалось создать hardware_config")
                    return None
                
                # Создаем временного пользователя
                temp_login = f"temp_{mac_address.replace(':', '')[:12]}"
                print(f"Создаем временного пользователя: {temp_login}")
                temp_user_id = cls.create_user(temp_login, computer_password, temp_login, 'client')
                
                if temp_user_id is None:
                    print("Не удалось создать временного пользователя")
                    return None
                
                # Обновляем last_login у пользователя
                cursor.execute("UPDATE user SET last_login = NOW() WHERE user_id = %s", (temp_user_id,))
                
                print("Создаем запись в computer...")
                cursor.execute("""
                    INSERT INTO computer 
                    (user_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'client', 1, NOW(), NOW())
                """, (temp_user_id, os_id, hardware_config_id, hostname, mac_address))
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
                
                print("=== РЕГИСТРАЦИЯ ЖЕЛЕЗА УСПЕШНО ЗАВЕРШЕНА ===")
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'login': temp_login,
                    'password': computer_password,
                    'user_id': temp_user_id,
                    'role_id': 1,  # client
                    'is_new': True,
                    'session_id': session_id,
                    'session_token': session_token,
                    'needs_auth': False  # уже авторизован через временного пользователя
                }
        except Exception as e:
            print(f"ОШИБКА регистрации: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def bind_user_to_computer(cls, computer_id: int, user_id: int) -> bool:
        """Привязка пользователя к компьютеру"""
        connection = cls.get_connection()
        if not connection:
            return False
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE computer SET user_id = %s WHERE computer_id = %s
                """, (user_id, computer_id))
                connection.commit()
                return True
        except Exception as e:
            print(f"Ошибка привязки пользователя: {e}")
            return False
        finally:
            connection.close()
    
    @classmethod
    def create_client_account(cls, computer_id: int, login: str = None) -> Optional[Dict[str, Any]]:
        """Создание аккаунта клиента и привязка к компьютеру"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                # Получаем данные компьютера
                cursor.execute("""
                    SELECT mac_address FROM computer WHERE computer_id = %s
                """, (computer_id,))
                computer_data = cursor.fetchone()
                
                if not computer_data:
                    print("Компьютер не найден")
                    return None
                
                mac_address = computer_data['mac_address']
                
                if login is None:
                    login = f"client_{mac_address.replace(':', '')[:12]}"
                
                # Генерируем пароль
                unique_id = HardwareIDGenerator.generate_unique_id()
                password = unique_id[:16]
                
                print(f"Создаем аккаунт клиента: {login}")
                
                # Создаем пользователя
                user_id = cls.create_user(login, password, login, 'client')
                
                if user_id is None:
                    print("Не удалось создать пользователя")
                    return None
                
                # Привязываем пользователя к компьютеру
                if not cls.bind_user_to_computer(computer_id, user_id):
                    print("Не удалось привязать пользователя к компьютеру")
                    return None
                
                # Обновляем тип компьютера
                cursor.execute("""
                    UPDATE computer SET computer_type = 'client', last_online = NOW()
                    WHERE computer_id = %s
                """, (computer_id,))
                connection.commit()
                
                # Создаем сессию
                cursor.execute("SELECT hostname FROM computer WHERE computer_id = %s", (computer_id,))
                comp_info = cursor.fetchone()
                hostname = comp_info['hostname'] if comp_info else socket.gethostname()
                
                session_id = cls.create_session(computer_id, hostname)
                
                cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                token_data = cursor.fetchone()
                session_token = token_data['session_token'] if token_data else None
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'login': login,
                    'password': password,
                    'user_id': user_id,
                    'role_id': 1,  # client
                    'computer_type': 'client',
                    'is_new': True,
                    'session_id': session_id,
                    'session_token': session_token
                }
        except Exception as e:
            print(f"Ошибка создания аккаунта клиента: {e}")
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
    
    @classmethod
    def add_user_action(cls, action_type: str, description: str, session_id: int, 
                       computer_id: int, user_id: int = None, is_remote: bool = False,
                       details: Dict = None) -> Optional[int]:
        """Добавление действия пользователя в систему"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_action 
                    (action_type, description, session_id, computer_id, user_id, is_remote, details, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (action_type, description, session_id, computer_id, user_id, 
                      1 if is_remote else 0, json.dumps(details) if details else None))
                action_id = cursor.lastrowid
                connection.commit()
                return action_id
        except Exception as e:
            print(f"Ошибка добавления действия пользователя: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def add_system_event(cls, event_type: str, severity: int, description: str,
                        computer_id: int, session_id: int = None) -> Optional[int]:
        """Добавление системного события"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO system_event 
                    (computer_id, session_id, event_type, severity, description, timestamp)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (computer_id, session_id, event_type, severity, description))
                event_id = cursor.lastrowid
                connection.commit()
                return event_id
        except Exception as e:
            print(f"Ошибка добавления системного события: {e}")
            return None
        finally:
            connection.close()
    
    @classmethod
    def check_hardware_changed(cls, computer_id: int) -> bool:
        """Проверяет, изменилось ли железо у компьютера"""
        connection = cls.get_connection()
        if not connection:
            return False
        
        try:
            current_config_id = cls.get_or_create_hardware_config()
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT hardware_config_id FROM computer WHERE computer_id = %s
                """, (computer_id,))
                result = cursor.fetchone()
                
                if result:
                    return result['hardware_config_id'] != current_config_id
                return False
        except Exception as e:
            print(f"Ошибка проверки железа: {e}")
            return False
        finally:
            connection.close()
    
    @classmethod
    def add_new_computer_for_user(cls, user_id: int) -> Optional[Dict[str, Any]]:
        """Добавление нового компьютера для существующего пользователя (при смене железа)"""
        connection = cls.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                hostname = socket.gethostname()
                mac_address = HardwareIDGenerator.get_mac_address()
                
                os_id = cls.get_or_create_os()
                hardware_config_id = cls.get_or_create_hardware_config()
                
                if hardware_config_id is None:
                    return None
                
                # Получаем роль пользователя
                cursor.execute("""
                    SELECT role_id FROM user WHERE user_id = %s
                """, (user_id,))
                user_data = cursor.fetchone()
                
                if not user_data:
                    return None
                
                role_id = user_data['role_id']
                computer_type = 'admin' if role_id in (2, 3) else 'client'
                
                cursor.execute("""
                    INSERT INTO computer 
                    (user_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, NOW(), NOW())
                """, (user_id, os_id, hardware_config_id, hostname, mac_address, computer_type))
                computer_id = cursor.lastrowid
                connection.commit()
                
                network_info = cls.get_network_info()
                cls.update_ip_address(computer_id, network_info)
                
                session_id = cls.create_session(computer_id, hostname)
                
                cursor.execute("SELECT session_token FROM session WHERE session_id = %s", (session_id,))
                token_data = cursor.fetchone()
                session_token = token_data['session_token'] if token_data else None
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'user_id': user_id,
                    'role_id': role_id,
                    'computer_type': computer_type,
                    'is_new': True,
                    'session_id': session_id,
                    'session_token': session_token
                }
        except Exception as e:
            print(f"Ошибка добавления нового компьютера: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def register_computer_for_user(cls, user_id: int, force_rebind: bool = False) -> Optional[Dict[str, Any]]:
        """Регистрация компьютера с привязкой к пользователю (вызывается после авторизации)
        
        Args:
            user_id: ID пользователя
            force_rebind: Принудительная перепривязка (если True - игнорирует предупреждение о другом пользователе)
        """
        print("=== РЕГИСТРАЦИЯ КОМПЬЮТЕРА С ПРИВЯЗКОЙ К ПОЛЬЗОВАТЕЛЮ ===")
        
        connection = cls.get_connection()
        if not connection:
            print("ОШИБКА: Нет подключения к БД")
            return None
        
        try:
            with connection.cursor() as cursor:
                hostname = socket.gethostname()
                mac_address = HardwareIDGenerator.get_mac_address()
                
                print(f"Хостнейм: {hostname}")
                print(f"MAC: {mac_address}")
                print(f"User ID: {user_id}")
                
                # Проверяем, не зарегистрирован ли уже компьютер с таким MAC
                cursor.execute("""
                    SELECT computer_id, hostname, user_id, hardware_config_id
                    FROM computer WHERE mac_address = %s
                """, (mac_address,))
                
                existing = cursor.fetchone()
                
                if existing:
                    print(f"Компьютер уже существует с ID: {existing['computer_id']}")
                    
                    current_user_id = existing.get('user_id')
                    
                    # Если компьютер привязан к другому пользователю
                    if current_user_id is not None and current_user_id != user_id:
                        if not force_rebind:
                            # Возвращаем информацию о том, что компьютер привязан к другому
                            print(f"Компьютер привязан к другому пользователю (user_id: {current_user_id})")
                            
                            # Получаем данные другого пользователя
                            cursor.execute("SELECT login FROM user WHERE user_id = %s", (current_user_id,))
                            other_user = cursor.fetchone()
                            other_login = other_user['login'] if other_user else 'Unknown'
                            
                            return {
                                'computer_id': existing['computer_id'],
                                'hostname': hostname,
                                'mac_address': mac_address,
                                'user_id': user_id,
                                'hardware_config_id': existing.get('hardware_config_id'),
                                'hardware_changed': False,
                                'is_new': False,
                                'already_bound': True,
                                'other_user_login': other_login,
                                'other_user_id': current_user_id
                            }
                        else:
                            # Принудительная перепривязка
                            print(f"Перепривязываем компьютер от пользователя {current_user_id} к {user_id}")
                            cursor.execute("""
                                UPDATE computer 
                                SET user_id = %s, hostname = %s, last_online = NOW()
                                WHERE computer_id = %s
                            """, (user_id, hostname, existing['computer_id']))
                            connection.commit()
                    elif current_user_id is None:
                        # Компьютер без пользователя - привязываем
                        cursor.execute("""
                            UPDATE computer 
                            SET user_id = %s, hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (user_id, hostname, existing['computer_id']))
                        connection.commit()
                        print(f"Компьютер {existing['computer_id']} привязан к пользователю {user_id}")
                    else:
                        # Обновляем данные (тот же пользователь)
                        cursor.execute("""
                            UPDATE computer SET hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (hostname, existing['computer_id']))
                        connection.commit()
                    
                    hardware_config_id = cls.get_or_create_hardware_config()
                    if hardware_config_id and existing.get('hardware_config_id') != hardware_config_id:
                        cls.update_computer_hardware_config(existing['computer_id'], hardware_config_id)
                    
                    network_info = cls.get_network_info()
                    cls.update_ip_address(existing['computer_id'], network_info)
                    
                    # Проверяем, изменилось ли железо
                    hardware_changed = existing.get('hardware_config_id') != hardware_config_id
                    
                    # Получаем роль пользователя для типа компьютера
                    cursor.execute("SELECT role_id FROM user WHERE user_id = %s", (user_id,))
                    user_data = cursor.fetchone()
                    role_id = user_data['role_id'] if user_data else 1
                    
                    # Обновляем тип компьютера
                    computer_type = 'admin' if role_id in (2, 3) else 'client'
                    cursor.execute("""
                        UPDATE computer SET computer_type = %s WHERE computer_id = %s
                    """, (computer_type, existing['computer_id']))
                    connection.commit()
                    
                    return {
                        'computer_id': existing['computer_id'],
                        'hostname': hostname,
                        'mac_address': mac_address,
                        'user_id': user_id,
                        'hardware_config_id': hardware_config_id,
                        'hardware_changed': hardware_changed,
                        'is_new': False,
                        'already_bound': False
                    }
                
                # Создаем новый компьютер с привязкой к пользователю
                print("Создаем новую запись о компьютере...")
                
                os_id = cls.get_or_create_os()
                hardware_config_id = cls.get_or_create_hardware_config()
                
                if hardware_config_id is None:
                    print("ОШИБКА: не удалось создать hardware_config")
                    return None
                
                # Получаем роль пользователя для типа компьютера
                cursor.execute("SELECT role_id FROM user WHERE user_id = %s", (user_id,))
                user_data = cursor.fetchone()
                role_id = user_data['role_id'] if user_data else 1
                computer_type = 'admin' if role_id in (2, 3) else 'client'
                
                print(f"Создаем запись в computer для пользователя {user_id}...")
                cursor.execute("""
                    INSERT INTO computer 
                    (user_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, NOW(), NOW())
                """, (user_id, os_id, hardware_config_id, hostname, mac_address, computer_type))
                computer_id = cursor.lastrowid
                connection.commit()
                
                print(f"Создан новый компьютер с ID: {computer_id}")
                
                network_info = cls.get_network_info()
                cls.update_ip_address(computer_id, network_info)
                
                print("=== РЕГИСТРАЦИЯ КОМПЬЮТЕРА УСПЕШНО ЗАВЕРШЕНА ===")
                
                return {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'mac_address': mac_address,
                    'user_id': user_id,
                    'hardware_config_id': hardware_config_id,
                    'hardware_changed': False,
                    'is_new': True,
                    'already_bound': False
                }
        except Exception as e:
            print(f"ОШИБКА регистрации: {e}")
            print(traceback.format_exc())
            return None
        finally:
            connection.close()
    
    @classmethod
    def rebind_computer_to_user(cls, computer_id: int, new_user_id: int) -> bool:
        """Перепривязка компьютера к другому пользователю"""
        connection = cls.get_connection()
        if not connection:
            return False
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE computer 
                    SET user_id = %s, last_online = NOW()
                    WHERE computer_id = %s
                """, (new_user_id, computer_id))
                connection.commit()
                print(f"Компьютер {computer_id} перепривязан к пользователю {new_user_id}")
                return True
        except Exception as e:
            print(f"Ошибка перепривязки: {e}")
            return False
        finally:
            connection.close()
