import requests
import json
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import socket
import platform
import hashlib
import bcrypt

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
        """Регистрация компьютера для пользователя"""
        try:
            hardware_id = HardwareIDGenerator.generate_unique_id()
            hostname = socket.gethostname()
            mac_address = HardwareIDGenerator.get_mac_address()
            
            # Получаем информацию о железе
            cpu_model = HardwareIDGenerator.get_cpu_serial()
            ram_total = cls._get_ram_total()
            storage_total = cls._get_storage_total()
            
            # Сначала пробуем зарегистрировать
            try:
                response = requests.post(
                    f"{API_BASE_URL}/api/computers/register",
                    json={
                        "user_id": user_id,
                        "hardware_hash": hardware_id,
                        "hostname": hostname,
                        "mac_address": mac_address,
                        "cpu_model": cpu_model[:100],
                        "ram_total_gb": ram_total,
                        "storage_total_gb": storage_total,
                        "force_rebind": force_rebind
                    },
                    headers=cls._headers(),
                    timeout=15
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get('success'):
                    return data['data']
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 409:
                    # Компьютер уже существует - ищем его по hardware_hash и обновляем пользователя
                    print("Компьютер уже зарегистрирован, пробуем перепривязать к новому пользователю...")
                    
                    # Получаем список компьютеров и ищем наш
                    computers = cls.get_computers()
                    target_computer = None
                    
                    if computers and isinstance(computers, list):
                        for comp in computers:
                            if isinstance(comp, dict) and comp.get('hardware_hash') == hardware_id:
                                target_computer = comp
                                break
                    
                    if target_computer and isinstance(target_computer, dict):
                        # Обновляем пользователя для существующего компьютера
                        computer_id = target_computer.get('computer_id')
                        if computer_id:
                            try:
                                update_response = requests.put(
                                    f"{API_BASE_URL}/api/computers/{computer_id}",
                                    json={
                                        "user_id": user_id,
                                        "hostname": hostname,
                                        "mac_address": mac_address
                                    },
                                    headers=cls._headers(),
                                    timeout=15
                                )
                                update_response.raise_for_status()
                                update_data = update_response.json()
                                
                                if update_data.get('success'):
                                    print(f"✅ Компьютер успешно перепривязан к пользователю ID: {user_id}")
                                    return target_computer
                            except Exception as update_err:
                                print(f"❌ Ошибка обновления компьютера: {update_err}")
            
            return None
        except Exception as e:
            print(f"Ошибка регистрации/перепривязки компьютера: {e}")
            return None
    
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
            
            # Логируем запрос для отладки
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
                cls.current_session_id = data['data']['session_id']
                return cls.current_session_id
            return None
        except Exception as e:
            print(f"Ошибка создания сессии: {e}")
            return None

    @classmethod
    def close_session(cls, session_id: int = None) -> bool:
        """Закрыть сессию"""
        try:
            sid = session_id if session_id is not None else cls.current_session_id
            
            if not sid:
                return False
            
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
            return True
        except Exception as e:
            print(f"Ошибка закрытия сессии: {e}")
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