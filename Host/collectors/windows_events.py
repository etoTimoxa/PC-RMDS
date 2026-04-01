import sys
import subprocess
import json
import re
import os
from datetime import datetime, timedelta
from typing import List, Dict, Callable, Optional

from utils.constants import CRITICAL_EVENT_IDS, USER_ACTION_TYPES

# ID событий Windows для перезагрузки и выключения
RESTART_SHUTDOWN_EVENT_IDS = [1074, 1076, 2001, 2004, 1000, 1001, 41, -2147482574]


class WindowsEventCollector:
    
    _last_record_numbers: Dict[str, int] = {}
    _last_collection_time: datetime = None
    _user_action_callback: Optional[Callable] = None
    _last_system_state: Dict[str, bool] = {
        'was_shutting_down': False,
        'last_power_state': None
    }
    
    @staticmethod
    def get_severity(event_type: int, event_id: int = None) -> str:
        """Определяет критичность события (Windows)"""
        # Windows event types
        EVENTLOG_ERROR_TYPE = 1
        EVENTLOG_WARNING_TYPE = 2
        EVENTLOG_INFORMATION_TYPE = 4
        EVENTLOG_AUDIT_SUCCESS = 8
        EVENTLOG_AUDIT_FAILURE = 16
        
        if event_type == EVENTLOG_ERROR_TYPE:
            if event_id in CRITICAL_EVENT_IDS:
                return 'critical'
            return 'error'
        elif event_type == EVENTLOG_WARNING_TYPE:
            return 'warning'
        elif event_type == EVENTLOG_INFORMATION_TYPE:
            return 'info'
        elif event_type == EVENTLOG_AUDIT_SUCCESS:
            return 'info'
        elif event_type == EVENTLOG_AUDIT_FAILURE:
            return 'warning'
        return 'info'
    
    @staticmethod
    def get_journalctl_severity(priority: str) -> str:
        """Определяет критичность события (Linux journalctl)"""
        priority_map = {
            '0': 'critical',
            '1': 'critical', 
            '2': 'critical',
            '3': 'error',
            '4': 'warning',
            '5': 'info',
            '6': 'info',
            '7': 'info'
        }
        return priority_map.get(priority, 'info')
    
    @classmethod
    def get_new_events(cls, logs: List[str] = None) -> List[Dict]:
        """Получает новые события (кроссплатформенно)"""
        if sys.platform == 'win32':
            return cls._get_new_events_windows(logs)
        else:
            return cls._get_new_events_linux()
    
    @classmethod
    def get_events_last_30min(cls) -> List[Dict]:
        """Получает события за последние 30 минут (кроссплатформенно)"""
        if sys.platform == 'win32':
            return cls._get_events_last_30min_windows()
        else:
            return cls._get_events_last_30min_linux()
    
    @classmethod
    def _get_new_events_windows(cls, logs: List[str] = None) -> List[Dict]:
        """Получает новые события Windows"""
        try:
            import win32evtlog
            import win32evtlogutil
            import win32security
        except ImportError:
            print("win32evtlog не установлен. Только для Windows.")
            return []
        
        if logs is None:
            logs = ['System', 'Application']
        
        all_events = []
        
        for log_name in logs:
            try:
                hand = win32evtlog.OpenEventLog(None, log_name)
                num_records = win32evtlog.GetNumberOfEventLogRecords(hand)
                last_record = cls._last_record_numbers.get(log_name, 0)
                
                if num_records > last_record:
                    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                    records_to_read = num_records - last_record
                    events_data = win32evtlog.ReadEventLog(hand, flags, records_to_read)
                    
                    if events_data:
                        for event in reversed(events_data):
                            severity = cls.get_severity(event.EventType, event.EventID)
                            
                            message = ""
                            try:
                                message = win32evtlogutil.SafeFormatMessage(event, log_name)
                            except:
                                try:
                                    if event.StringInserts:
                                        message = ' '.join(event.StringInserts)
                                    else:
                                        message = f"Event ID: {event.EventID}, Source: {event.SourceName}"
                                except:
                                    message = f"Event ID: {event.EventID}"
                            
                            user_info = None
                            if event.Sid is not None:
                                try:
                                    domain, user, typ = win32security.LookupAccountSid(None, event.Sid)
                                    user_info = f"{domain}\\{user}"
                                except:
                                    user_info = str(event.Sid)
                            
                            all_events.append({
                                'log': log_name.lower(),
                                'event_id': event.EventID,
                                'source': event.SourceName,
                                'severity': severity,
                                'event_type': 'error' if severity in ['critical', 'error'] else severity,
                                'time': event.TimeGenerated.strftime('%Y-%m-%d %H:%M:%S'),
                                'message': message[:2000] if message else '',
                                'category': event.EventCategory,
                                'user': user_info,
                                'record_number': event.RecordNumber
                            })
                    
                    cls._last_record_numbers[log_name] = num_records
                
                win32evtlog.CloseEventLog(hand)
                
            except Exception as e:
                print(f"Ошибка чтения журнала {log_name}: {e}")
        
        if all_events:
            cls._last_collection_time = datetime.now()
        
        return all_events
    
    @classmethod
    def _get_events_last_30min_windows(cls) -> List[Dict]:
        """Получает события Windows за последние 30 минут"""
        try:
            import win32evtlog
            import win32evtlogutil
            import win32security
        except ImportError:
            print("win32evtlog не установлен. Только для Windows.")
            return []
        
        logs = ['System', 'Application']
        all_events = []
        cutoff_time = datetime.now() - timedelta(minutes=30)
        MAX_EVENTS = 500
        
        for log_name in logs:
            try:
                hand = win32evtlog.OpenEventLog(None, log_name)
                
                num_records = win32evtlog.GetNumberOfEventLogRecords(hand)
                cls._last_record_numbers[log_name] = num_records
                
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                
                while len(all_events) < MAX_EVENTS:
                    events_data = win32evtlog.ReadEventLog(hand, flags, 0)
                    if not events_data:
                        break
                    
                    for event in events_data:
                        event_time = event.TimeGenerated
                        if event_time < cutoff_time:
                            continue
                        
                        severity = cls.get_severity(event.EventType, event.EventID)
                        
                        message = ""
                        try:
                            message = win32evtlogutil.SafeFormatMessage(event, log_name)
                        except:
                            try:
                                if event.StringInserts:
                                    message = ' '.join(event.StringInserts)
                                else:
                                    message = f"Event ID: {event.EventID}, Source: {event.SourceName}"
                            except:
                                message = f"Event ID: {event.EventID}"
                        
                        user_info = None
                        if event.Sid is not None:
                            try:
                                domain, user, typ = win32security.LookupAccountSid(None, event.Sid)
                                user_info = f"{domain}\\{user}"
                            except:
                                user_info = str(event.Sid)
                        
                        all_events.append({
                            'log': log_name.lower(),
                            'event_id': event.EventID,
                            'source': event.SourceName,
                            'severity': severity,
                            'event_type': 'error' if severity in ['critical', 'error'] else severity,
                            'time': event_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'message': message[:500] if message else '',
                            'category': event.EventCategory,
                            'user': user_info,
                            'record_number': event.RecordNumber
                        })
                        
                        if len(all_events) >= MAX_EVENTS:
                            break
                
                win32evtlog.CloseEventLog(hand)
                
            except Exception as e:
                print(f"Ошибка чтения журнала {log_name}: {e}")
        
        if all_events:
            cls._last_collection_time = datetime.now()
        
        return all_events
    
    @classmethod
    def _get_new_events_linux(cls) -> List[Dict]:
        """Получает новые события Linux (journalctl или fallback на файлы логов)"""
        all_events = []
        
        # Способ 1: Через journalctl (если есть systemd)
        try:
            if cls._last_collection_time:
                time_str = cls._last_collection_time.strftime('%Y-%m-%d %H:%M:%S')
                cmd = ['journalctl', '--since', time_str, '-o', 'json', '--no-pager']
            else:
                cmd = ['journalctl', '--since', '30 minutes ago', '-o', 'json', '--no-pager']
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        
                        priority = entry.get('PRIORITY', '6')
                        severity = cls.get_journalctl_severity(priority)
                        
                        all_events.append({
                            'log': 'system',
                            'event_id': 0,
                            'source': entry.get('SYSLOG_IDENTIFIER', 'unknown'),
                            'severity': severity,
                            'event_type': 'error' if severity in ['critical', 'error'] else severity,
                            'time': entry.get('__REALTIME_TIMESTAMP', '')[:19].replace('T', ' '),
                            'message': entry.get('MESSAGE', '')[:500],
                            'category': 0,
                            'user': entry.get('_UID', None)
                        })
                    except json.JSONDecodeError:
                        continue
                
                if all_events:
                    cls._last_collection_time = datetime.now()
                    return all_events
        except Exception as e:
            print(f"journalctl недоступен, используем fallback: {e}")
        
        # Способ 2: Чтение файлов логов (fallback если нет journalctl)
        all_events = cls._get_events_from_log_files()
        
        if all_events:
            cls._last_collection_time = datetime.now()
        
        return all_events
    
    @classmethod
    def _get_events_from_log_files(cls) -> List[Dict]:
        """Читает события из файлов логов Linux (fallback метод)"""
        all_events = []
        MAX_EVENTS = 500
        
        # Определяем возможные пути к логам
        log_paths = [
            '/var/log/syslog',           # Debian/Ubuntu
            '/var/log/messages',         # CentOS/RHEL/Fedora
            '/var/log/system.log',       # Некоторые дистрибутивы
            '/var/log/auth.log',         # Debian/Ubuntu (авторизация)
            '/var/log/secure',           # CentOS/RHEL (авторизация)
        ]
        
        # Время для фильтрации (последние 30 минут)
        if cls._last_collection_time:
            cutoff_time = cls._last_collection_time
        else:
            cutoff_time = datetime.now() - timedelta(minutes=30)
        
        for log_path in log_paths:
            if not os.path.exists(log_path):
                continue
            
            try:
                with open(log_path, 'r') as f:
                    lines = f.readlines()
                    
                    for line in lines[-MAX_EVENTS:]:  # Читаем последние MAX_EVENTS строк
                        if not line.strip():
                            continue
                        
                        # Парсим строку лога (формат: "Mon DD HH:MM:SS hostname process[pid]: message")
                        parts = line.strip().split(' ', 4)
                        if len(parts) < 4:
                            continue
                        
                        # Определяем критичность по ключевым словам
                        line_lower = line.lower()
                        if 'error' in line_lower or 'fail' in line_lower:
                            severity = 'error'
                        elif 'warning' in line_lower or 'warn' in line_lower:
                            severity = 'warning'
                        elif 'critical' in line_lower or 'crit' in line_lower:
                            severity = 'critical'
                        else:
                            severity = 'info'
                        
                        # Пытаемся извлечь имя процесса
                        source = 'unknown'
                        if len(parts) > 3:
                            source_part = parts[3].split('[')[0].split(':')[0].strip()
                            if source_part:
                                source = source_part
                        
                        all_events.append({
                            'log': 'system',
                            'event_id': 0,
                            'source': source,
                            'severity': severity,
                            'event_type': 'error' if severity in ['critical', 'error'] else severity,
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'message': line.strip()[:500],
                            'category': 0,
                            'user': None
                        })
                        
                        if len(all_events) >= MAX_EVENTS:
                            break
                
            except Exception as e:
                print(f"Ошибка чтения {log_path}: {e}")
        
        return all_events
    
    @classmethod
    def _get_events_last_30min_linux(cls) -> List[Dict]:
        """Получает события Linux за последние 30 минут через journalctl"""
        all_events = []
        MAX_EVENTS = 500
        
        try:
            cmd = ['journalctl', '--since', '30 minutes ago', '-o', 'json', '--no-pager', '-n', str(MAX_EVENTS)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        
                        priority = entry.get('PRIORITY', '6')
                        severity = cls.get_journalctl_severity(priority)
                        
                        all_events.append({
                            'log': 'system',
                            'event_id': 0,
                            'source': entry.get('SYSLOG_IDENTIFIER', 'unknown'),
                            'severity': severity,
                            'event_type': 'error' if severity in ['critical', 'error'] else severity,
                            'time': entry.get('__REALTIME_TIMESTAMP', '')[:19].replace('T', ' '),
                            'message': entry.get('MESSAGE', '')[:500],
                            'category': 0,
                            'user': entry.get('_UID', None)
                        })
                        
                        if len(all_events) >= MAX_EVENTS:
                            break
                    except json.JSONDecodeError:
                        continue
        
        except Exception as e:
            print(f"Ошибка чтения journalctl: {e}")
        
        if all_events:
            cls._last_collection_time = datetime.now()
        
        return all_events
    
    @classmethod
    def get_last_collection_time(cls) -> datetime:
        return cls._last_collection_time
    
    @classmethod
    def should_collect_events(cls) -> bool:
        if cls._last_collection_time is None:
            return True
        minutes_since_last = (datetime.now() - cls._last_collection_time).total_seconds() / 60
        return minutes_since_last >= 30
    
    @classmethod
    def set_user_action_callback(cls, callback: Callable[[str, str, dict], None]):
        """Устанавливает callback для логирования действий пользователя.
        
        Callback принимает: (action_type, description, details)
        """
        cls._user_action_callback = callback
    
    @classmethod
    def detect_restart_shutdown_events(cls, events: List[Dict]) -> List[Dict]:
        """Определяет события перезагрузки/выключения в списке событий.
        
        Возвращает список обнаруженных событий с дополнительной информацией.
        """
        detected_actions = []
        
        for event in events:
            event_id = event.get('event_id')
            log_name = event.get('log', '').lower()
            message = event.get('message', '').lower()
            user = event.get('user')
            source = event.get('source', '')
            time_str = event.get('time', '')
            
            # Проверяем ID события
            is_restart_shutdown = event_id in RESTART_SHUTDOWN_EVENT_IDS
            
            # Проверяем сообщение на ключевые слова
            restart_keywords = ['перезагрузка', 'restart', 'reboot', 'shutdown', 'выключение', 'завершение работы']
            is_restart_shutdown = is_restart_shutdown or any(kw in message for kw in restart_keywords)
            
            # Проверяем код события -2147482574 (User32: перезапуск) - инициировано пользователем/процессом
            # Это событие "Перезапустить" от RuntimeBroker.exe - пользователь нажал кнопку перезагрузки/выключения
            if event_id == -2147482574 or event_id == 2147482574:
                # Определяем тип действия (перезагрузка или выключение) по сообщению
                message_lower = event.get('message', '').lower()
                if 'перезапу' in message_lower or 'restart' in message_lower:
                    action_type = 'windows_restart'
                else:
                    action_type = 'windows_shutdown'
                
                # Определяем, было ли действие удалённым
                is_remote = False
                remote_keywords = ['удаленн', 'remote', 'rstrui']
                if any(kw in message_lower for kw in remote_keywords):
                    is_remote = True
                
                # Определяем тип пользователя на основе того, кто выполнил действие
                # Для события от User32 - это локальный пользователь (клиент)
                user_type = 'client'
                if user:
                    user_upper = user.upper()
                    if 'NT AUTHORITY' in user_upper or 'SYSTEM' in user_upper:
                        user_type = 'system'
                    elif 'ADMIN' in user_upper or user in ['Тимоха', 'Administrator']:
                        user_type = 'admin'
                
                action_info = {
                    'event_id': event_id,
                    'action_type': action_type,
                    'user': user,
                    'user_type': user_type,
                    'is_remote': is_remote,
                    'source': source,
                    'time': time_str,
                    'message': event.get('message', '')
                }
                
                detected_actions.append(action_info)
                
                if cls._user_action_callback:
                    description = USER_ACTION_TYPES.get(action_type, {}).get('description', 'Перезагрузка Windows')
                    details = {
                        'user': user,
                        'user_type': user_type,
                        'is_remote': is_remote,
                        'source': source,
                        'event_id': event_id,
                        'message': event.get('message', '')
                    }
                    try:
                        cls._user_action_callback(action_type, description, details)
                    except Exception as e:
                        print(f"Ошибка в user_action_callback: {e}")
            
            # Проверяем код события 1074 - инициировано процессом или удалённо
            if event_id == 1074 and log_name == 'system':
                # Это событие инициированного выключения/перезагрузки
                # Определяем тип (restart или shutdown)
                is_restart = 'перезагруз' in message.lower() or 'restart' in message.lower() or 'reboot' in message.lower()
                
                # Определяем, было ли действие удалённым
                is_remote = False
                remote_keywords = ['удаленн', 'remote', 'rstrui', 'shutdown /i', 'shutdown /m', 'завершение работы удаленн']
                if any(kw in message.lower() for kw in remote_keywords):
                    is_remote = True
                
                # Определяем тип действия и пользователя
                if is_remote:
                    # Удалённая перезагрузка/выключение (через админ-панель)
                    action_type = 'remote_restart' if is_restart else 'remote_shutdown'
                    user_type = 'admin'
                else:
                    # Системная перезагрузка/выключение (обновление, завершение работы и т.д.)
                    action_type = 'system_restart' if is_restart else 'system_shutdown'
                    user_type = 'system'
                
                action_info = {
                    'event_id': event_id,
                    'action_type': action_type,
                    'user': user,
                    'user_type': user_type,
                    'is_remote': is_remote,
                    'source': source,
                    'time': time_str,
                    'message': event.get('message', '')
                }
                
                detected_actions.append(action_info)
                
                # Вызываем callback если установлен
                if cls._user_action_callback:
                    description = USER_ACTION_TYPES.get(action_type, {}).get('description', action_type)
                    details = {
                        'user': user,
                        'user_type': user_type,
                        'is_remote': is_remote,
                        'source': source,
                        'event_id': event_id,
                        'message': event.get('message', '')
                    }
                    try:
                        cls._user_action_callback(action_type, description, details)
                    except Exception as e:
                        print(f"Ошибка в user_action_callback: {e}")
            
            # Событие 41 - критическое выключение (без корректного завершения)
            elif event_id == 41 and log_name == 'system':
                action_type = 'system_shutdown'  # Аварийное выключение системы
                action_info = {
                    'event_id': event_id,
                    'action_type': action_type,
                    'user': 'SYSTEM',
                    'user_type': 'system',
                    'is_remote': False,
                    'source': 'Kernel-General',
                    'time': time_str,
                    'message': 'Критическое выключение без корректного завершения работы'
                }
                detected_actions.append(action_info)
                
                if cls._user_action_callback:
                    description = USER_ACTION_TYPES.get(action_type, {}).get('description', 'Аварийное выключение компьютера')
                    details = {
                        'user': 'SYSTEM',
                        'user_type': 'system',
                        'is_remote': False,
                        'source': 'Kernel-General',
                        'event_id': event_id,
                        'message': 'Критическое выключение без корректного завершения работы'
                    }
                    try:
                        cls._user_action_callback(action_type, description, details)
                    except Exception as e:
                        print(f"Ошибка в user_action_callback: {e}")
        
        return detected_actions
    
    @classmethod
    def check_for_system_shutdown(cls) -> bool:
        """Проверяет, началась ли перезагрузка или выключение системы.
        
        Использует Windows API для определения состояния системы.
        Возвращает True если система инициировала выключение.
        """
        if sys.platform != 'win32':
            return False
        
        try:
            import ctypes
            from ctypes import wintypes
            
            # Запрашиваем флаги завершения работы
            EWX_LOGOFF = 0x00000000
            EWX_SHUTDOWN = 0x00000001
            EWX_REBOOT = 0x00000002
            EWX_FORCE = 0x00000004
            EWX_FORCEIFHUNG = 0x00000010
            
            # Проверяем, был ли инициализирован выход
            # Использузм GetSystemPowerStatus для проверки состояния
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", wintypes.BYTE),
                    ("BatteryFlag", wintypes.BYTE),
                    ("BatteryLifePercent", wintypes.BYTE),
                    ("SystemStatusFlag", wintypes.BYTE),
                    ("BatteryLifeTime", wintypes.DWORD),
                    ("BatteryFullLifeTime", wintypes.DWORD)
                ]
            
            status = SYSTEM_POWER_STATUS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
            
            return False
            
        except Exception as e:
            print(f"Ошибка проверки состояния системы: {e}")
            return False
    
    @classmethod
    def get_system_power_status(cls) -> dict:
        """Возвращает текущее состояние питания системы."""
        status = {
            'ac_line_status': 'Unknown',
            'battery_flag': 'Unknown',
            'battery_percent': None,
            'shutting_down': False
        }
        
        if sys.platform != 'win32':
            return status
        
        try:
            import ctypes
            from ctypes import wintypes
            
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", wintypes.BYTE),
                    ("BatteryFlag", wintypes.BYTE),
                    ("BatteryLifePercent", wintypes.BYTE),
                    ("SystemStatusFlag", wintypes.BYTE),
                    ("BatteryLifeTime", wintypes.DWORD),
                    ("BatteryFullLifeTime", wintypes.DWORD)
                ]
            
            power_status = SYSTEM_POWER_STATUS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power_status))
            
            # ACLineStatus: 0=Offline, 1=Online, 255=Unknown
            if power_status.ACLineStatus == 0:
                status['ac_line_status'] = 'Offline'
            elif power_status.ACLineStatus == 1:
                status['ac_line_status'] = 'Online'
            
            # BatteryFlag
            if power_status.BatteryFlag & 128:  # High
                status['battery_flag'] = 'High'
            elif power_status.BatteryFlag & 48:  # Charging or NoSystemBattery
                status['battery_flag'] = 'Charging'
            elif power_status.BatteryFlag & 8:  # Low
                status['battery_flag'] = 'Low'
            elif power_status.BatteryFlag & 4:  # Critical
                status['battery_flag'] = 'Critical'
            
            # BatteryLifePercent: 0-100, 255=Unknown
            if power_status.BatteryLifePercent != 255:
                status['battery_percent'] = power_status.BatteryLifePercent
            
        except Exception as e:
            print(f"Ошибка получения состояния питания: {e}")
        
        return status
