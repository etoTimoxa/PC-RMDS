import requests
import json
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import socket
import platform
import hashlib

from utils.constants import API_BASE_URL, STATUS_ACTIVE, STATUS_DISCONNECTED
from core.hardware_id import HardwareIDGenerator


class APIClient:
    current_session_id: Optional[int] = None
    current_computer_id: Optional[int] = None
    auth_token: Optional[str] = None
    
    @classmethod
    def get_connection(cls):
        """Заглушка для совместимости"""
        return cls
    
    @classmethod
    def cursor(cls):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return True
            def execute(self, *args, **kwargs): return True
            def fetchone(self): return None
            def fetchall(self): return []
        return Cursor()
    
    @classmethod
    def execute(cls, *args, **kwargs): return True
    @classmethod
    def fetchone(cls): return None
    @classmethod
    def commit(cls): return True
    @classmethod
    def __enter__(cls): return cls
    @classmethod
    def __exit__(cls, *args): return True
    
    @classmethod
    def set_current_session(cls, computer_id: int, session_id: int):
        cls.current_computer_id = computer_id
        cls.current_session_id = session_id
    
    @staticmethod
    def _headers():
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if APIClient.auth_token:
            headers['Authorization'] = f'Bearer {APIClient.auth_token}'
        return headers

    # ==============================================
    # АВТОРИЗАЦИЯ / АУТЕНТИФИКАЦИЯ
    # ==============================================
    
    @classmethod
    def login(cls, login: str, password: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/login",
                json={"login": login, "password": password},
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                cls.auth_token = data['data'].get('token')
                return data['data']['user']
            return None
        except Exception as e:
            print(f"Ошибка авторизации: {e}")
            return None
    
    @classmethod
    def register(cls, login: str, password: str, full_name: str) -> Optional[int]:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/register",
                json={"login": login, "password": password, "full_name": full_name},
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data'].get('user_id')
            return None
        except Exception as e:
            print(f"Ошибка регистрации: {e}")
            return None
    
    @classmethod
    def logout(cls) -> bool:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/logout",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            cls.auth_token = None
            cls.current_computer_id = None
            cls.current_session_id = None
            return True
        except Exception as e:
            print(f"Ошибка выхода: {e}")
            return False

    @classmethod
    def register_computer_for_user(cls, user_id: int, force_rebind: bool = False) -> Optional[Dict[str, Any]]:
        """Регистрация компьютера для пользователя с полной информацией о железе"""
        try:
            hardware_id = HardwareIDGenerator.generate_unique_id()
            hostname = socket.gethostname()
            mac_address = HardwareIDGenerator.get_mac_address()
            
            # Получаем ПОЛНУЮ информацию о железе
            hardware_info = HardwareIDGenerator.get_full_hardware_info()
            
            # Получаем IP адрес
            ip_address = cls._get_ip_address()
            
            # Формируем payload с правильными именами полей для сервера
            payload = {
                "user_id": user_id,
                "hardware_hash": hardware_id,
                "hostname": hostname,
                "mac_address": mac_address,
                "ip_address": ip_address,
                
                # Поля для hardware_config
                "cpu_model": hardware_info.get('cpu_model', 'Unknown'),
                "cpu_cores": hardware_info.get('cpu_cores', 0),
                "ram_total": hardware_info.get('ram_total', 0),
                "storage_total": hardware_info.get('storage_total', 0),
                "gpu_model": hardware_info.get('gpu_model', 'Unknown'),
                "motherboard": hardware_info.get('motherboard', 'Unknown'),
                "bios_version": hardware_info.get('bios_version', 'Unknown'),
                
                # Информация об ОС
                "os_name": hardware_info.get('os_name', 'Unknown'),
                "os_version": hardware_info.get('os_version', 'Unknown'),
                "os_architecture": hardware_info.get('os_architecture', 'x64'),
                
                # Даты
                "detected_at": hardware_info.get('detected_at'),
                "updated_at": hardware_info.get('updated_at'),
                
                "force_rebind": force_rebind
            }
            
            # Логируем для отладки
            print(f"🔍 Регистрация компьютера:")
            print(f"   user_id: {user_id}")
            print(f"   hostname: {hostname}")
            print(f"   mac_address: {mac_address}")
            print(f"   CPU Model: {payload['cpu_model']}")
            print(f"   CPU Cores: {payload['cpu_cores']}")
            print(f"   RAM Total: {payload['ram_total']} GB")
            print(f"   Storage Total: {payload['storage_total']} GB")
            print(f"   GPU Model: {payload['gpu_model']}")
            print(f"   Motherboard: {payload['motherboard']}")
            print(f"   BIOS Version: {payload['bios_version']}")
            print(f"   OS: {payload['os_name']} {payload['os_version']}")
            
            response = requests.post(
                f"{API_BASE_URL}/api/computers/register",
                json=payload,
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                print(f"✅ Компьютер успешно зарегистрирован!")
                print(f"   computer_id: {data['data'].get('computer_id')}")
                print(f"   hardware_config_id: {data['data'].get('hardware_config_id')}")
                print(f"   os_id: {data['data'].get('os_id')}")
                return data['data']
            return None
        except Exception as e:
            print(f"❌ Ошибка регистрации компьютера: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   Ответ сервера: {e.response.text}")
            return None
    
    @staticmethod
    def _get_ip_address() -> str:
        """Получает текущий IP адрес"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"
    
    @staticmethod
    def _get_ram_total() -> float:
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024**3), 2)
        except:
            return 0.0
    
    @staticmethod
    def _get_storage_total() -> float:
        try:
            import psutil
            return round(psutil.disk_usage('/').total / (1024**3), 2)
        except:
            return 0.0
    
    # ==============================================
    # КОМПЬЮТЕРЫ
    # ==============================================
    
    @classmethod
    def get_computers(cls) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения компьютеров: {e}")
            return None
    
    @classmethod
    def get_computer(cls, computer_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/{computer_id}",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения компьютера: {e}")
            return None
    
    @classmethod
    def update_computer_status(cls, computer_id: int, is_online: bool, session_id: int = None) -> bool:
        try:
            response = requests.put(
                f"{API_BASE_URL}/api/computers/{computer_id}/status",
                json={"is_online": is_online, "session_id": session_id},
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('success', False)
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
            return False
    
    @classmethod
    def get_computer_ip_addresses(cls, computer_id: int) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/{computer_id}/ip-addresses",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data', {}).get('ip_addresses') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения IP: {e}")
            return None
    
    @classmethod
    def get_computer_sessions(cls, computer_id: int, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/{computer_id}/sessions",
                params={"limit": limit},
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data', {}).get('sessions') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения сессий: {e}")
            return None
    
    # ==============================================
    # СЕССИИ
    # ==============================================
    
    @classmethod
    def create_session(cls, computer_id: int, user_id: int = None, session_token: str = None) -> Optional[int]:
        """Создать новую сессию"""
        try:
            if session_token is None:
                session_token = f"{socket.gethostname()}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            
            payload = {
                "computer_id": computer_id,
                "session_token": session_token,
                "status_id": 1
            }
            if user_id:
                payload["user_id"] = user_id
            
            print(f"[DEBUG] Отправляем запрос на создание сессии:")
            print(f"[DEBUG] URL: {API_BASE_URL}/api/sessions")
            print(f"[DEBUG] BODY: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            
            response = requests.post(
                f"{API_BASE_URL}/api/sessions",
                json=payload,
                headers=cls._headers(),
                timeout=10
            )
            
            print(f"[DEBUG] Статус ответа: {response.status_code}")
            print(f"[DEBUG] Ответ сервера: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                session_id = data['data']['session_id']
                cls.current_session_id = session_id
                print(f"✅ Сессия создана: ID={session_id}")
                return session_id
            return None
        except Exception as e:
            print(f"❌ Ошибка создания сессии: {e}")
            return None

    @classmethod
    def close_session(cls, session_id: int = None) -> bool:
        """Закрыть сессию"""
        try:
            sid = session_id if session_id is not None else cls.current_session_id
            
            if not sid:
                print("⚠️ Нет активной сессии для закрытия")
                return False
            
            print(f"🔵 Закрытие сессии {sid}")
            
            response = requests.put(
                f"{API_BASE_URL}/api/sessions/{sid}",
                json={
                    "status_id": 2,
                    "end_time": datetime.now().isoformat()
                },
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            
            if cls.current_computer_id:
                cls.update_computer_status(cls.current_computer_id, False, sid)
            
            cls.current_session_id = None
            print(f"✅ Сессия {sid} закрыта")
            return True
        except Exception as e:
            print(f"❌ Ошибка закрытия сессии: {e}")
            return False

    @classmethod
    def update_session_activity(cls, session_id: int) -> bool:
        try:
            response = requests.put(
                f"{API_BASE_URL}/api/sessions/{session_id}",
                json={"last_activity": datetime.now().isoformat()},
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('success', False)
        except Exception as e:
            print(f"Ошибка обновления активности: {e}")
            return False

    @classmethod
    def update_json_sent_count(cls, session_id: int, count: int) -> bool:
        try:
            response = requests.put(
                f"{API_BASE_URL}/api/sessions/{session_id}",
                json={"json_sent_count": count},
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('success', False)
        except Exception as e:
            print(f"Ошибка обновления счетчика: {e}")
            return False

    # ==============================================
    # ПОЛЬЗОВАТЕЛИ
    # ==============================================
    
    @classmethod
    def get_users(cls) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/users",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения пользователей: {e}")
            return None
    
    @classmethod
    def get_user(cls, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/users/{user_id}",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения пользователя: {e}")
            return None
    
    @classmethod
    def create_user(cls, login: str, password: str, full_name: str, role: str = 'client') -> Optional[int]:
        """Создание нового пользователя"""
        return cls.register(login, password, full_name)
    
    # ==============================================
    # МЕТРИКИ
    # ==============================================
    
    @classmethod
    def upload_metrics_file(cls, file_path: str) -> bool:
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                headers = {}
                if cls.auth_token:
                    headers['Authorization'] = f'Bearer {cls.auth_token}'
                
                response = requests.post(
                    f"{API_BASE_URL}/api/metrics/upload",
                    files=files,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                return data.get('success', False)
        except Exception as e:
            print(f"Ошибка загрузки метрик: {e}")
            return False
    
    # ==============================================
    # СТАТУСЫ
    # ==============================================
    
    @classmethod
    def get_statuses(cls) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/statuses",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения статусов: {e}")
            return None
    
    # ==============================================
    # ПАНЕЛЬ ДАННЫХ
    # ==============================================
    
    @classmethod
    def get_dashboard_stats(cls) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/dashboard/stats",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return None


DatabaseManager = APIClient