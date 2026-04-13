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
        """Заглушка для совместимости. Всегда возвращает сам класс"""
        return cls
    
    @classmethod
    def cursor(cls):
        """Заглушка для совместимости со старым кодом"""
        class Cursor:
            def __enter__(self):
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                return True
            
            def execute(self, *args, **kwargs):
                return True
            
            def fetchone(self):
                return None
            
            def fetchall(self):
                return []
        
        return Cursor()
    
    @classmethod
    def execute(cls, *args, **kwargs):
        """Заглушка для совместимости"""
        return True
    
    @classmethod
    def fetchone(cls):
        """Заглушка для совместимости"""
        return None
    
    @classmethod
    def commit(cls):
        """Заглушка для совместимости"""
        return True
    
    @classmethod
    def __enter__(cls):
        """Заглушка для поддержки менеджера контекста with connection.cursor() as cursor"""
        return cls
    
    @classmethod
    def __exit__(cls, exc_type, exc_val, exc_tb):
        """Заглушка для поддержки менеджера контекста"""
        return True
    
    @classmethod
    def set_current_session(cls, computer_id: int, session_id: int):
        cls.current_computer_id = computer_id
        cls.current_session_id = session_id
    
    @staticmethod
    def _headers():
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        if APIClient.auth_token:
            headers['Authorization'] = f'Bearer {APIClient.auth_token}'
        return headers

    # ==============================================
    # АВТОРИЗАЦИЯ / АУТЕНТИФИКАЦИЯ
    # ==============================================
    
    @classmethod
    def login(cls, login: str, password: str) -> Optional[Dict[str, Any]]:
        """Аутентификация по логину и паролю"""
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
        """Регистрация нового пользователя"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/register",
                json={
                    "login": login,
                    "password": password,
                    "full_name": full_name
                },
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
        """Завершение сессии"""
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
            hardware_id = HardwareIDGenerator.get_hardware_id()
            hostname = socket.gethostname()
            
            response = requests.post(
                f"{API_BASE_URL}/api/computers/register",
                json={
                    "user_id": user_id,
                    "hardware_id": hardware_id,
                    "hostname": hostname,
                    "force_rebind": force_rebind
                },
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка регистрации компьютера: {e}")
            return None
    
    # ==============================================
    # КОМПЬЮТЕРЫ
    # ==============================================
    
    @classmethod
    def get_computers(cls) -> Optional[List[Dict[str, Any]]]:
        """Получение списка всех компьютеров"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка получения компьютеров: {e}")
            return None
    
    @classmethod
    def get_computer(cls, computer_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о конкретном компьютере"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/{computer_id}",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка получения компьютера: {e}")
            return None
    
    @classmethod
    def update_computer_status(cls, computer_id: int, is_online: bool, session_id: int = None) -> bool:
        """Обновление статуса компьютера"""
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
            print(f"Ошибка обновления статуса компьютера: {e}")
            return False
    
    @classmethod
    def get_computer_ip_addresses(cls, computer_id: int) -> Optional[List[Dict[str, Any]]]:
        """Получение IP адресов компьютера"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/{computer_id}/ip-addresses",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']['ip_addresses']
            return None
        except Exception as e:
            print(f"Ошибка получения IP адресов: {e}")
            return None
    
    @classmethod
    def get_computer_sessions(cls, computer_id: int, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """Получение сессий компьютера"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/{computer_id}/sessions",
                params={"limit": limit},
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']['sessions']
            return None
        except Exception as e:
            print(f"Ошибка получения сессий: {e}")
            return None
    
    # ==============================================
    # ПОЛЬЗОВАТЕЛИ
    # ==============================================
    
    @classmethod
    def get_users(cls) -> Optional[List[Dict[str, Any]]]:
        """Получение списка всех пользователей"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/users",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка получения пользователей: {e}")
            return None
    
    @classmethod
    def get_user(cls, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/users/{user_id}",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка получения пользователя: {e}")
            return None
    
    # ==============================================
    # МЕТРИКИ
    # ==============================================
    
    @classmethod
    def upload_metrics_file(cls, file_path: str) -> bool:
        """Загрузка файла метрик в облако"""
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
        """Получение списка статусов"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/statuses",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка получения статусов: {e}")
            return None
    
    # ==============================================
    # ПАНЕЛЬ ДАННЫХ
    # ==============================================
    
    @classmethod
    def get_dashboard_stats(cls) -> Optional[Dict[str, Any]]:
        """Получение статистики для дашборда"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/dashboard/stats",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return data['data']
            return None
        except Exception as e:
            print(f"Ошибка получения статистики дашборда: {e}")
            return None


# Для полной совместимости со старым кодом
DatabaseManager = APIClient