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
    _last_ip: Optional[str] = None  # Сохраняем последний IP
    
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

    @classmethod
    def get(cls, url: str, params: dict = None, **kwargs):
        """Общий метод GET запросов для совместимости"""
        try:
            full_url = API_BASE_URL + (url if url.startswith('/api') else f'/api{url}')
            response = requests.get(
                full_url,
                headers=cls._headers(),
                params=params,
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            try:
                result = response.json()
                if not isinstance(result, dict):
                    return {'success': False, 'data': []}
                return result
            except:
                return {'success': False, 'data': []}
        except Exception as e:
            print(f"GET запрос ошибка {url}: {e}")
            return {'success': False, 'data': []}

    @classmethod
    def post(cls, url: str, json: dict = None, **kwargs):
        """Общий метод POST запросов для совместимости"""
        try:
            full_url = API_BASE_URL + (url if url.startswith('/api') else f'/api{url}')
            response = requests.post(
                full_url,
                headers=cls._headers(),
                json=json,
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"POST запрос ошибка {url}: {e}")
            return None

    @classmethod
    def put(cls, url: str, json: dict = None, **kwargs):
        """Общий метод PUT запросов для совместимости"""
        try:
            full_url = API_BASE_URL + (url if url.startswith('/api') else f'/api{url}')
            response = requests.put(
                full_url,
                headers=cls._headers(),
                json=json,
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"PUT запрос ошибка {url}: {e}")
            return None

    @classmethod
    def delete(cls, url: str, **kwargs):
        """Общий метод DELETE запросов для совместимости"""
        try:
            full_url = API_BASE_URL + (url if url.startswith('/api') else f'/api{url}')
            response = requests.delete(
                full_url,
                headers=cls._headers(),
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"DELETE запрос ошибка {url}: {e}")
            return None

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
    def _get_ip_address(cls) -> str:
        """Получает текущий IP адрес"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"

    @classmethod
    def register_computer_for_user(cls, user_id: int, force_rebind: bool = False) -> Optional[Dict[str, Any]]:
        """Регистрация компьютера для пользователя с полной информацией о железе"""
        try:
            hardware_id = HardwareIDGenerator.generate_unique_id()
            hostname = socket.gethostname()
            mac_address = HardwareIDGenerator.get_mac_address()
            
            hardware_info = HardwareIDGenerator.get_full_hardware_info()
            current_ip = cls._get_ip_address()
            
            # Получаем существующую информацию о компьютере, если он уже есть
            existing_computer = None
            try:
                # Ищем компьютер по MAC адресу
                computers_result = cls.get('/computers')
                if computers_result and computers_result.get('success'):
                    computers = computers_result.get('data', {}).get('computers', [])
                    for comp in computers:
                        if comp.get('mac_address') == mac_address:
                            existing_computer = comp
                            break
            except Exception as e:
                print(f"Ошибка поиска существующего компьютера: {e}")
            
            payload = {
                "user_id": user_id,
                "hardware_hash": hardware_id,
                "hostname": hostname,
                "mac_address": mac_address,
                "ip_address": current_ip,
                
                "cpu_model": hardware_info.get('cpu_model', 'Unknown'),
                "cpu_cores": hardware_info.get('cpu_cores', 0),
                "ram_total": hardware_info.get('ram_total', 0),
                "storage_total": hardware_info.get('storage_total', 0),
                "gpu_model": hardware_info.get('gpu_model', 'Unknown'),
                "motherboard": hardware_info.get('motherboard', 'Unknown'),
                "bios_version": hardware_info.get('bios_version', 'Unknown'),
                
                "os_name": hardware_info.get('os_name', 'Unknown'),
                "os_version": hardware_info.get('os_version', 'Unknown'),
                "os_architecture": hardware_info.get('os_architecture', 'x64'),
                
                "detected_at": hardware_info.get('detected_at'),
                "updated_at": hardware_info.get('updated_at'),
                
                "force_rebind": force_rebind
            }
            
            # Если компьютер уже существует, сохраняем group_id и inventory_number
            if existing_computer:
                if existing_computer.get('group_id'):
                    payload['group_id'] = existing_computer['group_id']
                if existing_computer.get('inventory_number'):
                    payload['inventory_number'] = existing_computer['inventory_number']
                if existing_computer.get('description'):
                    payload['description'] = existing_computer['description']
                print(f"📌 Сохраняем существующие данные: group_id={payload.get('group_id')}, inventory={payload.get('inventory_number')}")
            
            print(f"🔍 Регистрация компьютера:")
            print(f"   user_id: {user_id}")
            print(f"   hostname: {hostname}")
            print(f"   mac_address: {mac_address}")
            print(f"   current_ip: {current_ip}")
            
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
                cls._last_ip = current_ip
                return data['data']
            return None
        except Exception as e:
            print(f"❌ Ошибка регистрации компьютера: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   Ответ сервера: {e.response.text}")
            return None
    
    @classmethod
    def update_computer_ip(cls, computer_id: int, ip_address: str) -> bool:
        """Обновляет IP адрес компьютера, только если он изменился"""
        if cls._last_ip == ip_address:
            print(f"IP адрес не изменился: {ip_address}, пропускаем")
            return True
        
        try:
            print(f"🔄 Обновление IP адреса компьютера {computer_id}: {ip_address}")
            response = requests.post(
                f"{API_BASE_URL}/api/computers/{computer_id}/ip",
                json={"ip_address": ip_address},
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            cls._last_ip = ip_address
            print(f"✅ IP адрес обновлен")
            return True
        except Exception as e:
            print(f"❌ Ошибка обновления IP: {e}")
            return False
    
    @classmethod
    def rebind_computer(cls, computer_id: int, user_id: int, computer_type: str) -> Optional[Dict[str, Any]]:
        """Перепривязывает компьютер к другому пользователю"""
        try:
            print(f"🔄 Перепривязка компьютера {computer_id} к пользователю {user_id} (тип: {computer_type})")
            
            response = cls.put(
                f"/api/computers/{computer_id}",
                json={
                    "user_id": user_id,
                    "computer_type": computer_type
                }
            )
            
            if response and response.get('success'):
                print(f"✅ Компьютер успешно перепривязан")
                return response.get('data')
            else:
                error = response.get('error', 'Неизвестная ошибка') if response else 'Нет ответа от сервера'
                print(f"❌ Ошибка перепривязки: {error}")
                return None
        except Exception as e:
            print(f"❌ Ошибка перепривязки: {e}")
            return None

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
    def update_computer(cls, computer_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обновление информации о компьютере (в том числе смена владельца, группы, инвентарного номера)"""
        try:
            response = requests.put(
                f"{API_BASE_URL}/api/computers/{computer_id}",
                json=data,
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            if result.get('success'):
                print(f"✅ Компьютер {computer_id} успешно обновлен")
                return result.get('data')
            return None
        except Exception as e:
            print(f"❌ Ошибка обновления компьютера {computer_id}: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   Ответ сервера: {e.response.text}")
            return None
    
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

    @classmethod
    def close_session(cls) -> bool:
        """Закрывает текущую сессию (статус = 2)"""
        return cls.close_session_by_id()
    
    # ==============================================
    # ГРУППЫ КОМПЬЮТЕРОВ
    # ==============================================
    
    @classmethod
    def get_computer_groups(cls) -> Optional[List[Dict[str, Any]]]:
        """Получить список всех групп компьютеров"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/computers/groups",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка получения групп: {e}")
            return None
    
    @classmethod
    def create_computer_group(cls, group_name: str, description: str = None) -> Optional[int]:
        """Создать новую группу компьютеров"""
        try:
            payload = {"group_name": group_name}
            if description:
                payload["description"] = description
            
            response = requests.post(
                f"{API_BASE_URL}/api/computers/groups",
                json=payload,
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data', {}).get('group_id') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка создания группы: {e}")
            return None
    
    @classmethod
    def update_computer_group(cls, group_id: int, group_name: str = None, description: str = None) -> bool:
        """Обновить группу компьютеров"""
        try:
            payload = {}
            if group_name:
                payload["group_name"] = group_name
            if description:
                payload["description"] = description
            
            response = requests.put(
                f"{API_BASE_URL}/api/computers/groups/{group_id}",
                json=payload,
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('success', False)
        except Exception as e:
            print(f"Ошибка обновления группы: {e}")
            return False
    
    @classmethod
    def delete_computer_group(cls, group_id: int) -> bool:
        """Удалить группу компьютеров"""
        try:
            response = requests.delete(
                f"{API_BASE_URL}/api/computers/groups/{group_id}",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('success', False)
        except Exception as e:
            print(f"Ошибка удаления группы: {e}")
            return False
    
    # ==============================================
    # УПРАВЛЕНИЕ ПАРОЛЯМИ
    # ==============================================
    
    @classmethod
    def reset_password(cls, reset_token: str, new_password: str) -> Optional[Dict[str, Any]]:
        """Сброс пароля по токену"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/computers/user/reset-password",
                json={"reset_token": reset_token, "new_password": new_password},
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка сброса пароля: {e}")
            return None

    @classmethod
    def request_password_reset(cls, user_id: int) -> Optional[Dict[str, Any]]:
        """Запрос на сброс пароля (создание токена)"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/computers/user/{user_id}/reset-password",
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка запроса сброса пароля: {e}")
            return None

    @classmethod
    def change_password(cls, user_id: int, old_password: str, new_password: str) -> Optional[Dict[str, Any]]:
        """Изменение пароля (требуется старый пароль)"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/computers/user/{user_id}/change-password",
                json={"old_password": old_password, "new_password": new_password},
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка изменения пароля: {e}")
            return None

    # ==============================================
    # СЕССИИ
    # ==============================================
    
    @classmethod
    def create_session(cls, computer_id: int, user_id: int = None, session_token: str = None) -> Optional[int]:
        """Создать новую сессию"""
        try:
            # ✅ Защита от двойного создания сессии
            if cls.current_session_id is not None:
                print(f"⚠️ Сессия уже существует (ID={cls.current_session_id}), пропускаем создание новой")
                return cls.current_session_id
                
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
    def close_session_by_id(cls, session_id: int = None) -> bool:
        """Закрывает сессию (статус = 2)"""
        try:
            # Если session_id не передан, используем текущий
            if session_id is None:
                session_id = cls.current_session_id
            
            if not session_id:
                print("⚠️ Нет ID сессии для закрытия")
                return False
            
            print(f"🔵 Закрытие сессии {session_id}")
            
            response = requests.put(
                f"{API_BASE_URL}/api/sessions/{session_id}",
                json={
                    "status_id": 2,
                "end_time": datetime.now().astimezone().isoformat()
                },
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                # Очищаем текущую сессию, если это она
                if cls.current_session_id == session_id:
                    cls.current_session_id = None
                
                print(f"✅ Сессия {session_id} закрыта")
                return True
            else:
                print(f"❌ Ошибка закрытия сессии: {data.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка закрытия сессии: {e}")
            return False

    @classmethod
    def update_session_activity(cls, session_id: int) -> bool:
        try:
            response = requests.put(
                f"{API_BASE_URL}/api/sessions/{session_id}",
                json={"last_activity": datetime.now().astimezone().isoformat()},
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
        # Определяем role_id по роли
        role_id = 1 if role == 'client' else 2
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/users",
                json={
                    "login": login,
                    "password": password,
                    "full_name": full_name,
                    "role_id": role_id,
                    "is_active": 1
                },
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data', {}).get('user_id') if data.get('success') else None
        except Exception as e:
            print(f"Ошибка создания пользователя: {e}")
            return None

    @classmethod
    def update_user(cls, user_id: int, data: Dict[str, Any]) -> bool:
        """Обновление данных пользователя"""
        try:
            response = requests.put(
                f"{API_BASE_URL}/api/users/{user_id}",
                json=data,
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            return result.get('success', False)
        except Exception as e:
            print(f"Ошибка обновления пользователя: {e}")
            return False

    @classmethod
    def delete_user(cls, user_id: int) -> bool:
        """Удаление пользователя"""
        try:
            response = requests.delete(
                f"{API_BASE_URL}/api/users/{user_id}",
                headers=cls._headers(),
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            return result.get('success', False)
        except Exception as e:
            print(f"Ошибка удаления пользователя: {e}")
            return False

    @classmethod
    def request_password_reset(cls, login: str) -> bool:
        """Запрос на сброс пароля по логину"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/password/reset-request",
                json={"login": login},
                headers=cls._headers(),
                timeout=15
            )
            response.raise_for_status()
            result = response.json()
            return result.get('success', False)
        except Exception as e:
            print(f"Ошибка запроса сброса пароля: {e}")
            return False
    
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