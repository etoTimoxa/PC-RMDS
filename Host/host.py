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
from datetime import datetime, timedelta, date
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
from typing import Optional, Dict, Any, List
import win32evtlog
import win32evtlogutil
import win32security
import win32api
import win32con
from ctypes import wintypes
import threading
import boto3
from botocore.config import Config
from pathlib import Path

# Настройка DPI для Windows
if platform.system() == "Windows":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTextEdit, QGroupBox, QMessageBox,
                            QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
                            QSpinBox, QDoubleSpinBox, QTabWidget, QSystemTrayIcon,
                            QMenu, QStatusBar, QFrame, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QAction, QIcon, QPixmap, QColor

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController


# ==================== ПРОВЕРКА ПРАВ АДМИНИСТРАТОРА ====================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return True
    except:
        return False


# ==================== КЛАСС ДЛЯ ГРУППИРОВКИ СОБЫТИЙ ====================
class EventGrouper:
    """Класс для группировки повторяющихся событий"""
    
    @staticmethod
    def get_event_key(event: Dict) -> str:
        """Создать ключ для группировки события"""
        message = event.get('message', '')
        # Убираем из сообщения временные метки и номера записей
        import re
        cleaned_message = re.sub(r'record number \d+', '', message, flags=re.IGNORECASE)
        cleaned_message = re.sub(r'Record Number: \d+', '', cleaned_message, flags=re.IGNORECASE)
        cleaned_message = re.sub(r'Event ID: \d+', '', cleaned_message, flags=re.IGNORECASE)
        cleaned_message = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', cleaned_message)
        
        return f"{event.get('log')}_{event.get('event_id')}_{event.get('source')}_{hash(cleaned_message)}"
    
    def group_events(self, events: List[Dict]) -> List[Dict]:
        """Сгруппировать повторяющиеся события"""
        grouped = {}
        
        for event in events:
            key = self.get_event_key(event)
            
            if key not in grouped:
                grouped[key] = {
                    'log': event.get('log'),
                    'event_id': event.get('event_id'),
                    'source': event.get('source'),
                    'severity': event.get('severity'),
                    'event_type': event.get('event_type'),
                    'message': event.get('message'),
                    'category': event.get('category'),
                    'user': event.get('user'),
                    'first_time': event.get('time'),
                    'last_time': event.get('time'),
                    'count': 1
                }
            else:
                grouped[key]['count'] += 1
                grouped[key]['last_time'] = event.get('time')
        
        # Преобразуем в список
        result = []
        for key, data in grouped.items():
            if data['count'] == 1:
                # Одиночное событие
                result.append({
                    'log': data['log'],
                    'event_id': data['event_id'],
                    'source': data['source'],
                    'severity': data['severity'],
                    'event_type': data['event_type'],
                    'time': data['first_time'],
                    'message': data['message'],
                    'category': data['category'],
                    'user': data['user'],
                    'is_grouped': False
                })
            else:
                # Групповое событие
                result.append({
                    'log': data['log'],
                    'event_id': data['event_id'],
                    'source': data['source'],
                    'severity': data['severity'],
                    'event_type': data['event_type'],
                    'first_time': data['first_time'],
                    'last_time': data['last_time'],
                    'count': data['count'],
                    'message': data['message'],
                    'category': data['category'],
                    'user': data['user'],
                    'is_grouped': True
                })
        
        return result


# ==================== КЛАСС ДЛЯ РАБОТЫ С JSON ЛОГАМИ ====================
class JSONLogger:
    """Класс для записи метрик и событий Windows в JSON файлы"""
    
    def __init__(self, temps_folder: str = None):
        if temps_folder is None:
            base_path = Path(__file__).parent
            self.temps_folder = base_path / "Temps"
        else:
            self.temps_folder = Path(temps_folder)
        
        self.temps_folder.mkdir(exist_ok=True)
        
        self.current_file = None
        self.current_date = None
        self.current_computer_name = None
        self.current_session_token = None
        self.lock = threading.Lock()
        
        self.previous_metrics = None
        self.anomaly_threshold = {
            'cpu_usage': 30,
            'ram_usage': 20,
            'disk_usage': 15
        }
        
        # Служебная папка для маркеров (не отправляется в облако)
        self.markers_folder = self.temps_folder / ".markers"
        self.markers_folder.mkdir(exist_ok=True)
        
        # Файл флага - были ли уже записаны события за 24 часа в текущем дне
        self.events_flag_file = self.markers_folder / "events_24h_loaded.json"
        self._load_events_flag()
    
    def _load_events_flag(self):
        """Загрузить флаг о загрузке событий за 24 часа"""
        self._events_loaded_date = None
        if self.events_flag_file.exists():
            try:
                with open(self.events_flag_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._events_loaded_date = data.get('date')
                    print(f"📋 Загружен флаг событий: дата={self._events_loaded_date}")
            except Exception as e:
                print(f"Ошибка загрузки флага: {e}")
    
    def _save_events_flag(self, date_str: str):
        """Сохранить флаг о загрузке событий за 24 часа"""
        try:
            with open(self.events_flag_file, 'w', encoding='utf-8') as f:
                json.dump({'date': date_str}, f)
            print(f"📋 Сохранен флаг событий: дата={date_str}")
        except Exception as e:
            print(f"Ошибка сохранения флага: {e}")
    
    def _clear_events_flag(self):
        """Очистить флаг о загрузке событий"""
        if self.events_flag_file.exists():
            try:
                self.events_flag_file.unlink()
                print(f"📋 Очищен флаг событий")
            except:
                pass
        self._events_loaded_date = None
    
    def set_session(self, computer_name: str, session_token: str):
        """Установить данные сессии"""
        self.current_computer_name = computer_name
        self.current_session_token = session_token
        
        old_date = self.current_date
        self.current_date = datetime.now().date()
        
        print(f"📅 Текущая дата: {self.current_date}, старая дата: {old_date}")
        
        # Если день изменился, очищаем флаг
        if old_date is not None and old_date != self.current_date:
            print(f"📅 День изменился, очищаем флаг")
            self._clear_events_flag()
        else:
            # Если день не изменился, перезагружаем флаг из файла
            self._load_events_flag()
        
        self.create_daily_file()
        
        # Проверяем, не нужно ли отправить файл за вчерашний день
        self.check_and_mark_yesterday_file()
        
        # Удаляем старые файлы (старше 2 дней)
        self.cleanup_old_files()
    
    def create_daily_file(self):
        """Создать файл для текущей даты (один файл на день)"""
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.current_computer_name)
        file_name = f"{clean_name}_{self.current_date.isoformat()}.json"
        self.current_file = self.temps_folder / file_name
        print(f"📁 Текущий файл: {self.current_file.name}")
        
        if not self.current_file.exists():
            self.save_records([])
    
    def save_records(self, records: List[Dict]):
        """Сохранить записи в файл"""
        if not self.current_file:
            return
        
        try:
            with self.lock:
                with open(self.current_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения JSON файла: {e}")
    
    def load_records(self) -> List[Dict]:
        """Загрузить все записи из файла"""
        if not self.current_file or not self.current_file.exists():
            return []
        
        try:
            with open(self.current_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except:
            return []
    
    def add_metric(self, metrics: Dict):
        """Добавить метрики системы с привязкой к токену сессии"""
        records = self.load_records()
        
        record = {
            'timestamp': datetime.now().isoformat(),
            'computer_name': self.current_computer_name,
            'session_token': self.current_session_token,
            'type': 'metric',
            'data': metrics
        }
        
        records.append(record)
        self.save_records(records)
        
        # Проверяем на аномалии
        if self.previous_metrics:
            self.check_anomalies(metrics)
        
        self.previous_metrics = metrics.copy()
    
    def add_windows_events(self, events: List[Dict], is_initial: bool = False):
        """Добавить события из журнала Windows с привязкой к токену сессии"""
        records = self.load_records()
        
        for event in events:
            if event.get('is_grouped'):
                # Групповое событие
                record = {
                    'computer_name': self.current_computer_name,
                    'session_token': self.current_session_token,
                    'type': 'windows_event_grouped',
                    'data': {
                        'log': event.get('log'),
                        'event_id': event.get('event_id'),
                        'source': event.get('source'),
                        'severity': event.get('severity'),
                        'event_type': event.get('event_type'),
                        'first_time': event.get('first_time'),
                        'last_time': event.get('last_time'),
                        'count': event.get('count'),
                        'message': event.get('message'),
                        'category': event.get('category'),
                        'user': event.get('user')
                    }
                }
            else:
                # Одиночное событие
                record = {
                    'timestamp': event.get('time', datetime.now().isoformat()),
                    'computer_name': self.current_computer_name,
                    'session_token': self.current_session_token,
                    'type': 'windows_event',
                    'data': {
                        'log': event.get('log'),
                        'event_id': event.get('event_id'),
                        'source': event.get('source'),
                        'severity': event.get('severity'),
                        'event_type': event.get('event_type'),
                        'message': event.get('message', ''),
                        'category': event.get('category', 0),
                        'user': event.get('user', None)
                    }
                }
            records.append(record)
        
        self.save_records(records)
        
        # Если это начальная загрузка за 24 часа, сохраняем флаг
        if is_initial:
            self._save_events_flag(self.current_date.isoformat())
            print(f"✅ Сохранен флаг: события за 24 часа загружены для {self.current_date}")
    
    def check_anomalies(self, current_metrics: Dict):
        """Проверить наличие аномалий в метриках"""
        anomalies = []
        
        for key, threshold in self.anomaly_threshold.items():
            if key in current_metrics and key in self.previous_metrics:
                current_value = current_metrics.get(key, 0)
                previous_value = self.previous_metrics.get(key, 0)
                
                if previous_value > 0:
                    change = abs(current_value - previous_value)
                    if change > threshold:
                        anomalies.append({
                            'metric': key,
                            'previous': previous_value,
                            'current': current_value,
                            'change': change
                        })
        
        if anomalies:
            # Добавляем предупреждение об аномалии
            records = self.load_records()
            record = {
                'timestamp': datetime.now().isoformat(),
                'computer_name': self.current_computer_name,
                'session_token': self.current_session_token,
                'type': 'windows_event',
                'data': {
                    'log': 'system',
                    'event_id': 0,
                    'source': 'Performance Monitor',
                    'severity': 'warning',
                    'event_type': 'warning',
                    'message': f"Обнаружены резкие скачки метрик: {anomalies}",
                    'category': 0,
                    'user': None
                }
            }
            records.append(record)
            self.save_records(records)
            
            # Помечаем файл для срочной отправки
            self.mark_for_urgent_upload()
    
    def get_file_path_for_date(self, target_date: date) -> Path:
        """Получить путь к файлу за определенную дату"""
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.current_computer_name)
        file_name = f"{clean_name}_{target_date.isoformat()}.json"
        return self.temps_folder / file_name
    
    def mark_for_urgent_upload(self):
        """Пометить текущий файл для срочной отправки"""
        if self.current_file:
            marker_file = self.markers_folder / f"urgent_{self.current_file.name}"
            try:
                with open(marker_file, 'w') as f:
                    f.write(self.current_file.name)
            except:
                pass
    
    def mark_for_end_of_day_upload(self):
        """Пометить файл для отправки в конце дня"""
        if self.current_file:
            marker_file = self.markers_folder / f"endofday_{self.current_file.name}"
            try:
                with open(marker_file, 'w') as f:
                    f.write(self.current_file.name)
            except:
                pass
    
    def check_and_mark_yesterday_file(self):
        """Проверить и пометить файл за вчерашний день для отправки"""
        yesterday = datetime.now().date() - timedelta(days=1)
        yesterday_file = self.get_file_path_for_date(yesterday)
        
        if yesterday_file.exists():
            sent_marker = self.markers_folder / f"sent_{yesterday_file.name}"
            if not sent_marker.exists():
                marker_file = self.markers_folder / f"endofday_{yesterday_file.name}"
                try:
                    with open(marker_file, 'w') as f:
                        f.write(yesterday_file.name)
                    print(f"📁 Файл за {yesterday} помечен для отправки")
                    return True
                except:
                    pass
        return False
    
    def mark_as_sent(self, file_name: str):
        """Пометить файл как отправленный"""
        sent_marker = self.markers_folder / f"sent_{file_name}"
        try:
            sent_marker.touch()
        except:
            pass
    
    def mark_today_as_sent(self):
        """Пометить сегодняшний файл как отправленный"""
        if self.current_file:
            self.mark_as_sent(self.current_file.name)
    
    def cleanup_old_files(self):
        """Удалить файлы старше 2 дней (оставить только текущий и предыдущий)"""
        try:
            current_date = self.current_date
            files_to_keep = set()
            
            # Добавляем текущий файл
            if self.current_file:
                files_to_keep.add(self.current_file.name)
            
            # Добавляем файл за вчерашний день
            yesterday = current_date - timedelta(days=1)
            yesterday_file = self.get_file_path_for_date(yesterday)
            if yesterday_file.exists():
                files_to_keep.add(yesterday_file.name)
            
            # Удаляем все остальные JSON файлы (не трогаем .markers)
            for file_path in self.temps_folder.glob("*.json"):
                if file_path.name not in files_to_keep:
                    try:
                        file_path.unlink()
                        print(f"🗑️ Удален старый файл: {file_path.name}")
                    except Exception as e:
                        print(f"Ошибка удаления {file_path.name}: {e}")
        except Exception as e:
            print(f"Ошибка очистки старых файлов: {e}")
    
    def events_loaded_today(self) -> bool:
        """Проверить, были ли загружены события за 24 часа в этом дне"""
        result = self._events_loaded_date == self.current_date.isoformat() if self.current_date else False
        print(f"📋 Проверка флага: загружены ли события для {self.current_date}? {result} (флаг: {self._events_loaded_date})")
        return result
    
    def switch_to_new_day(self):
        """Переключиться на новый день (вызывается в полночь)"""
        print(f"🌙 Переключение на новый день")
        # Помечаем текущий файл для отправки
        self.mark_for_end_of_day_upload()
        
        # Очищаем флаг загрузки событий для нового дня
        self._clear_events_flag()
        
        # Обновляем дату и создаем новый файл
        self.current_date = datetime.now().date()
        self.create_daily_file()


# ==================== КЛАСС ДЛЯ СБОРА СОБЫТИЙ WINDOWS ====================
class WindowsEventCollector:
    """Класс для сбора событий из журнала Windows с разделением по severity"""
    
    # Для хранения последних номеров записей
    _last_record_numbers = {}
    
    @staticmethod
    def get_severity(event_type: int, event_id: int = None) -> str:
        """Определить severity события"""
        # Критические события
        critical_event_ids = [1001, 1003, 1005, 1010, 1011, 1015, 1074, 1076, 1078, 1098, 1099, 1101]
        
        if event_type == win32evtlog.EVENTLOG_ERROR_TYPE:
            if event_id in critical_event_ids:
                return 'critical'
            return 'error'
        elif event_type == win32evtlog.EVENTLOG_WARNING_TYPE:
            return 'warning'
        elif event_type == win32evtlog.EVENTLOG_INFORMATION_TYPE:
            return 'info'
        elif event_type == win32evtlog.EVENTLOG_AUDIT_SUCCESS:
            return 'info'
        elif event_type == win32evtlog.EVENTLOG_AUDIT_FAILURE:
            return 'warning'
        return 'info'
    
    @staticmethod
    def get_new_events(logs: List[str] = None) -> List[Dict]:
        """Получить только новые события, которые появились с момента последнего сбора"""
        if logs is None:
            logs = ['System', 'Application']
        
        all_events = []
        
        for log_name in logs:
            try:
                hand = win32evtlog.OpenEventLog(None, log_name)
                num_records = win32evtlog.GetNumberOfEventLogRecords(hand)
                last_record = WindowsEventCollector._last_record_numbers.get(log_name, 0)
                
                if num_records > last_record:
                    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                    records_to_read = num_records - last_record
                    events_data = win32evtlog.ReadEventLog(hand, flags, records_to_read)
                    
                    if events_data:
                        for event in reversed(events_data):
                            severity = WindowsEventCollector.get_severity(event.EventType, event.EventID)
                            
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
                            
                            event_data = {
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
                            }
                            all_events.append(event_data)
                    
                    WindowsEventCollector._last_record_numbers[log_name] = num_records
                
                win32evtlog.CloseEventLog(hand)
                
            except Exception as e:
                print(f"Ошибка чтения журнала {log_name}: {e}")
        
        return all_events
    
    @staticmethod
    def get_all_events_last_24h() -> List[Dict]:
        """Получить все события за последние 24 часа (при первом запуске дня)"""
        logs = ['System', 'Application']
        all_events = []
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for log_name in logs:
            try:
                hand = win32evtlog.OpenEventLog(None, log_name)
                num_records = win32evtlog.GetNumberOfEventLogRecords(hand)
                WindowsEventCollector._last_record_numbers[log_name] = num_records
                
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                
                while True:
                    events_data = win32evtlog.ReadEventLog(hand, flags, 0)
                    if not events_data:
                        break
                    
                    for event in events_data:
                        event_time = event.TimeGenerated
                        if event_time < cutoff_time:
                            continue
                        
                        severity = WindowsEventCollector.get_severity(event.EventType, event.EventID)
                        
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
                        
                        event_data = {
                            'log': log_name.lower(),
                            'event_id': event.EventID,
                            'source': event.SourceName,
                            'severity': severity,
                            'event_type': 'error' if severity in ['critical', 'error'] else severity,
                            'time': event_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'message': message[:2000] if message else '',
                            'category': event.EventCategory,
                            'user': user_info,
                            'record_number': event.RecordNumber
                        }
                        all_events.append(event_data)
                        
                        if len(all_events) > 5000:
                            break
                    
                    if len(all_events) > 5000:
                        break
                
                win32evtlog.CloseEventLog(hand)
                
            except Exception as e:
                print(f"Ошибка чтения журнала {log_name}: {e}")
        
        return all_events


# ==================== КЛАСС ДЛЯ СБОРА МЕТРИК СИСТЕМЫ ====================
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
    def get_performance_metrics():
        try:
            return {
                "cpu_usage": psutil.cpu_percent(interval=1),
                "ram_usage": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "disk_usage": psutil.disk_usage('/').percent,
                "disk_used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
                "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                "network_sent_mb": round(psutil.net_io_counters().bytes_sent / (1024**2), 2),
                "network_recv_mb": round(psutil.net_io_counters().bytes_recv / (1024**2), 2),
                "uptime_seconds": time.time() - psutil.boot_time()
            }
        except:
            return {}


# ==================== КЛАСС ДЛЯ ОТПРАВКИ В ОБЛАЧНОЕ ХРАНИЛИЩЕ ====================
class CloudUploader:
    def __init__(self):
        self.ACCESS_KEY = "1TUFGD6LDS8S8DGRFYMU"
        self.SECRET_KEY = "Vq3kZWM8HSxcxZNv4qLw9l63J80mj9fBsd80KumS"
        self.ENDPOINT_URL = "https://s3.regru.cloud"
        self.BUCKET_NAME = "metrics-errors-logs"
        
        self.s3 = None
        self.temps_folder = Path(__file__).parent / "Temps"
        self.markers_folder = self.temps_folder / ".markers"
        
        self.init_s3_client()
    
    def init_s3_client(self):
        try:
            self.s3 = boto3.client(
                's3',
                endpoint_url=self.ENDPOINT_URL,
                aws_access_key_id=self.ACCESS_KEY,
                aws_secret_access_key=self.SECRET_KEY,
                config=Config(signature_version='s3v4')
            )
        except Exception as e:
            print(f"Ошибка инициализации S3: {e}")
            self.s3 = None
    
    def upload_file(self, file_path: Path) -> bool:
        if not self.s3 or not file_path.exists():
            return False
        
        try:
            object_name = file_path.name
            file_size = file_path.stat().st_size / 1024
            
            print(f"📤 Загрузка: {object_name} ({file_size:.1f} KB)")
            self.s3.upload_file(str(file_path), self.BUCKET_NAME, object_name)
            print(f"   ✅ {object_name} - загружен")
            return True
        except Exception as e:
            print(f"   ❌ {object_name}: {e}")
            return False
    
    def upload_end_of_day_files(self):
        uploaded = 0
        end_of_day_files = self.markers_folder.glob("endofday_*.json")
        
        for marker_file in end_of_day_files:
            try:
                with open(marker_file, 'r') as f:
                    file_name = f.read().strip()
                
                file_path = self.temps_folder / file_name
                sent_marker = self.markers_folder / f"sent_{file_name}"
                
                if file_path.exists() and not sent_marker.exists():
                    if self.upload_file(file_path):
                        sent_marker.touch()
                        uploaded += 1
                
                marker_file.unlink()
            except Exception as e:
                print(f"Ошибка: {e}")
        
        return uploaded
    
    def upload_urgent_files(self):
        uploaded = 0
        urgent_files = self.markers_folder.glob("urgent_*.json")
        
        for marker_file in urgent_files:
            try:
                with open(marker_file, 'r') as f:
                    file_name = f.read().strip()
                
                file_path = self.temps_folder / file_name
                sent_marker = self.markers_folder / f"sent_{file_name}"
                
                if file_path.exists() and not sent_marker.exists():
                    if self.upload_file(file_path):
                        sent_marker.touch()
                        uploaded += 1
                
                marker_file.unlink()
            except Exception as e:
                print(f"Ошибка: {e}")
        
        return uploaded
    
    def check_and_upload(self):
        uploaded = 0
        uploaded += self.upload_end_of_day_files()
        uploaded += self.upload_urgent_files()
        return uploaded


# ==================== КЛАСС ДЛЯ РАБОТЫ С БД ====================
class DatabaseManager:
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
    
    STATUS_ACTIVE = 1
    STATUS_DISCONNECTED = 2
    STATUS_TIMEOUT = 3
    STATUS_ERROR = 4
    STATUS_PENDING = 5
    
    @staticmethod
    def get_connection():
        try:
            return pymysql.connect(**DatabaseManager.DB_CONFIG)
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None
    
    @staticmethod
    def set_current_session(computer_id, session_id):
        DatabaseManager.current_computer_id = computer_id
        DatabaseManager.current_session_id = session_id
    
    @staticmethod
    def generate_session_token(computer_hostname: str) -> str:
        clean_hostname = re.sub(r'[^a-zA-Z0-9_-]', '_', computer_hostname)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"{clean_hostname}_{timestamp}"
    
    @staticmethod
    def create_session(computer_id: int, computer_hostname: str) -> Optional[int]:
        connection = DatabaseManager.get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE session 
                    SET status_id = %s,
                        end_time = NOW()
                    WHERE computer_id = %s AND status_id = %s
                """, (DatabaseManager.STATUS_DISCONNECTED, computer_id, DatabaseManager.STATUS_ACTIVE))
                
                session_token = DatabaseManager.generate_session_token(computer_hostname)
                
                cursor.execute("""
                    INSERT INTO session 
                    (computer_id, session_token, start_time, status_id, json_sent_count, error_count)
                    VALUES (%s, %s, NOW(), %s, 0, 0)
                """, (computer_id, session_token, DatabaseManager.STATUS_ACTIVE))
                
                session_id = cursor.lastrowid
                connection.commit()
                print(f"✅ Создана сессия: id={session_id}, token={session_token}")
                return session_id
        except Exception as e:
            print(f"Ошибка создания сессии: {e}")
            return None
        finally:
            connection.close()
    
    @staticmethod
    def update_session_activity(session_id: int):
        connection = DatabaseManager.get_connection()
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
    
    @staticmethod
    def update_session_end(session_id: int, status_id: int = None):
        if status_id is None:
            status_id = DatabaseManager.STATUS_DISCONNECTED
            
        connection = DatabaseManager.get_connection()
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
    
    @staticmethod
    def update_json_sent_count(session_id: int, count: int):
        connection = DatabaseManager.get_connection()
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
        except:
            pass
        finally:
            connection.close()
    
    @staticmethod
    def update_error_count(session_id: int, count: int):
        connection = DatabaseManager.get_connection()
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
    
    @staticmethod
    def get_or_create_hardware_config() -> Optional[int]:
        connection = DatabaseManager.get_connection()
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
    
    @staticmethod
    def update_ip_address(computer_id: int, ip_address: str):
        connection = DatabaseManager.get_connection()
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
                        cursor.execute("""
                            UPDATE computer SET hostname = %s, last_online = NOW()
                            WHERE computer_id = %s
                        """, (hostname, existing['computer_id']))
                        connection.commit()
                        
                        ip_address = DatabaseManager.get_local_ip()
                        DatabaseManager.update_ip_address(existing['computer_id'], ip_address)
                        session_id = DatabaseManager.create_session(existing['computer_id'], hostname)
                        
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
                
                cursor.execute("""
                    INSERT INTO credential (login, password_hash, is_active, created_at)
                    VALUES (%s, %s, 1, NOW())
                """, (computer_login, password_hash))
                credential_id = cursor.lastrowid
                
                os_id = DatabaseManager.get_or_create_os()
                hardware_config_id = DatabaseManager.get_or_create_hardware_config()
                
                cursor.execute("""
                    INSERT INTO computer 
                    (credential_id, os_id, hardware_config_id, hostname, mac_address, computer_type, is_online, last_online, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'client', 1, NOW(), NOW())
                """, (credential_id, os_id, hardware_config_id, hostname, mac_address))
                computer_id = cursor.lastrowid
                connection.commit()
                
                ip_address = DatabaseManager.get_local_ip()
                DatabaseManager.update_ip_address(computer_id, ip_address)
                session_id = DatabaseManager.create_session(computer_id, hostname)
                
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
                    
                    ip_address = DatabaseManager.get_local_ip()
                    DatabaseManager.update_ip_address(computer_data['computer_id'], ip_address)
                    session_id = DatabaseManager.create_session(computer_data['computer_id'], hostname)
                    
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
    
    @staticmethod
    def update_computer_status(computer_id: int, is_online: bool, session_id: int = None):
        connection = DatabaseManager.get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE computer SET is_online = %s, last_online = NOW()
                    WHERE computer_id = %s
                """, (1 if is_online else 0, computer_id))
                
                if session_id and not is_online:
                    DatabaseManager.update_session_end(session_id, DatabaseManager.STATUS_DISCONNECTED)
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


# ==================== КЛАСС ДЛЯ ГЕНЕРАЦИИ HARDWARE ID ====================
class HardwareIDGenerator:
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
        return hashlib.sha256(hardware_string.encode()).hexdigest()[:32]
    
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


# ==================== КЛАСС АГЕНТА ====================
class RemoteAgentThread(QThread):
    log_message = pyqtSignal(str)
    connection_status_changed = pyqtSignal(bool, int)
    client_connected = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    
    def __init__(self, relay_server, computer_data, screenshot_interval, quality=70):
        super().__init__()
        self.relay_server = relay_server
        self.computer_data = computer_data
        self.computer_id = computer_data['computer_id']
        self.session_id = computer_data['session_id']
        self.session_token = computer_data.get('session_token', '')
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
        
        # Инициализируем JSON логгер с токеном сессии
        self.json_logger = JSONLogger()
        self.json_logger.set_session(self.hostname, self.session_token)
        
        # Инициализируем загрузчик в облако
        self.cloud_uploader = CloudUploader()
        
        # Группировщик событий
        self.event_grouper = EventGrouper()
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        try:
            self.screen_width, self.screen_height = pyautogui.size()
        except:
            self.screen_width, self.screen_height = 1920, 1080
    
    def update_settings(self, screenshot_interval=None, quality=None):
        if screenshot_interval is not None:
            self.screenshot_interval = screenshot_interval
        if quality is not None:
            self.quality = quality
    
    def run(self):
        asyncio.run(self.agent_main())
    
    async def collect_initial_metrics_and_events(self):
        """Сбор начальных метрик и событий Windows при старте сессии"""
        # Собираем метрики всегда
        metrics = SystemInfoCollector.get_performance_metrics()
        self.json_logger.add_metric(metrics)
        self.log_message.emit(f"📊 Начальные метрики: CPU={metrics['cpu_usage']}%, RAM={metrics['ram_usage']}%")
        
        # Собираем события Windows за последние 24 часа ТОЛЬКО если в этом дне еще не загружали
        events_loaded = self.json_logger.events_loaded_today()
        self.log_message.emit(f"📋 Проверка: события за 24 часа уже загружены? {events_loaded}")
        
        if not events_loaded:
            self.log_message.emit("📋 Сбор событий Windows за последние 24 часа...")
            events = WindowsEventCollector.get_all_events_last_24h()
            
            if events:
                # Группируем повторяющиеся события
                grouped_events = self.event_grouper.group_events(events)
                
                self.json_logger.add_windows_events(grouped_events, is_initial=True)
                
                critical = len([e for e in grouped_events if e.get('severity') == 'critical'])
                errors = len([e for e in grouped_events if e.get('severity') == 'error'])
                warnings = len([e for e in grouped_events if e.get('severity') == 'warning'])
                grouped_count = len([e for e in grouped_events if e.get('is_grouped')])
                
                self.log_message.emit(f"📋 События Windows за 24 часа: всего {len(grouped_events)} записей (критических: {critical}, ошибок: {errors}, предупреждений: {warnings}, сгруппировано: {grouped_count})")
            else:
                self.log_message.emit("📋 События Windows: нет событий за последние 24 часа")
        else:
            self.log_message.emit("📋 События Windows уже загружены сегодня, пропускаем")
    
    async def collect_metrics_periodically(self):
        """Периодический сбор метрик (каждые 30 минут)"""
        while self.is_running:
            try:
                await asyncio.sleep(1800)  # 30 минут
                
                if not self.is_running:
                    break
                
                metrics = SystemInfoCollector.get_performance_metrics()
                self.json_logger.add_metric(metrics)
                self.log_message.emit(f"📊 Метрики: CPU={metrics['cpu_usage']}%, RAM={metrics['ram_usage']}%")
                
            except Exception as e:
                self.log_message.emit(f"Ошибка сбора метрик: {e}")
    
    async def collect_new_windows_events_periodically(self):
        """Периодический сбор НОВЫХ событий Windows (каждые 30 минут)"""
        while self.is_running:
            try:
                await asyncio.sleep(1800)  # 30 минут
                
                if not self.is_running:
                    break
                
                # Собираем только новые события
                self.log_message.emit("📋 Сбор новых событий Windows...")
                events = WindowsEventCollector.get_new_events()
                
                if events:
                    # Группируем повторяющиеся события
                    grouped_events = self.event_grouper.group_events(events)
                    
                    self.json_logger.add_windows_events(grouped_events, is_initial=False)
                    
                    critical = len([e for e in grouped_events if e.get('severity') == 'critical'])
                    errors = len([e for e in grouped_events if e.get('severity') == 'error'])
                    warnings = len([e for e in grouped_events if e.get('severity') == 'warning'])
                    grouped_count = len([e for e in grouped_events if e.get('is_grouped')])
                    
                    self.log_message.emit(f"📋 Новые события Windows: {len(grouped_events)} записей (критических: {critical}, ошибок: {errors}, предупреждений: {warnings}, сгруппировано: {grouped_count})")
                else:
                    self.log_message.emit("📋 Новые события Windows: нет")
                
            except Exception as e:
                self.log_message.emit(f"Ошибка сбора событий Windows: {e}")
    
    async def update_activity_periodically(self):
        """Обновление last_activity в БД (каждые 15 минут)"""
        while self.is_running and self.is_connected:
            try:
                await asyncio.sleep(900)  # 15 минут
                
                if self.session_id:
                    DatabaseManager.update_session_activity(self.session_id)
                    self.log_message.emit("💓 Обновлена last_activity")
                
            except Exception as e:
                self.log_message.emit(f"Ошибка обновления активности: {e}")
    
    async def check_and_upload_at_midnight(self):
        """Проверка и отправка файлов в полночь"""
        while self.is_running:
            try:
                now = datetime.now()
                next_midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
                seconds_until_midnight = (next_midnight - now).total_seconds()
                
                await asyncio.sleep(seconds_until_midnight)
                
                if not self.is_running:
                    break
                
                # Полночь наступила - переключаемся на новый день
                self.log_message.emit("🌙 Полночь - переключение на новый день")
                
                # Сохраняем старый файл для отправки и создаем новый
                old_file = self.json_logger.current_file
                self.json_logger.switch_to_new_day()
                
                # Помечаем старый файл для отправки
                if old_file and old_file.exists():
                    self.json_logger.mark_for_end_of_day_upload()
                    self.log_message.emit(f"📁 Файл {old_file.name} помечен для отправки")
                
                # Отправляем все помеченные файлы
                uploaded = self.cloud_uploader.check_and_upload()
                if uploaded > 0:
                    self.log_message.emit(f"☁️ Загружено {uploaded} файлов")
                    DatabaseManager.update_json_sent_count(self.session_id, uploaded)
                
                # Теперь загружаем события за последние 24 часа для нового дня
                self.log_message.emit("📋 Сбор событий Windows за последние 24 часа для нового дня...")
                events = WindowsEventCollector.get_all_events_last_24h()
                
                if events:
                    grouped_events = self.event_grouper.group_events(events)
                    self.json_logger.add_windows_events(grouped_events, is_initial=True)
                    
                    critical = len([e for e in grouped_events if e.get('severity') == 'critical'])
                    errors = len([e for e in grouped_events if e.get('severity') == 'error'])
                    warnings = len([e for e in grouped_events if e.get('severity') == 'warning'])
                    self.log_message.emit(f"📋 События за 24 часа для нового дня: {len(grouped_events)} (критических: {critical}, ошибок: {errors}, предупреждений: {warnings})")
                
            except Exception as e:
                self.log_message.emit(f"Ошибка проверки полуночи: {e}")
    
    async def check_and_upload_on_startup(self):
        """Проверка и отправка файлов при запуске"""
        uploaded = self.cloud_uploader.check_and_upload()
        if uploaded > 0:
            self.log_message.emit(f"☁️ Загружено {uploaded} файлов из прошлых сессий")
            DatabaseManager.update_json_sent_count(self.session_id, uploaded)
    
    async def check_urgent_upload(self):
        """Проверка срочных отправок (при аномалиях)"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
                uploaded = self.cloud_uploader.check_and_upload()
                if uploaded > 0:
                    self.log_message.emit(f"⚡ Срочная отправка: {uploaded} файлов")
                    
            except Exception as e:
                pass
    
    async def agent_main(self):
        reconnect_delay = 5
        
        # Проверяем и отправляем файлы при старте
        await self.check_and_upload_on_startup()
        
        # Собираем начальные метрики и события Windows
        await self.collect_initial_metrics_and_events()
        
        # Запускаем периодические задачи
        tasks = [
            asyncio.create_task(self.collect_metrics_periodically()),
            asyncio.create_task(self.collect_new_windows_events_periodically()),
            asyncio.create_task(self.update_activity_periodically()),
            asyncio.create_task(self.check_and_upload_at_midnight()),
            asyncio.create_task(self.check_urgent_upload())
        ]
        
        while self.is_running:
            try:
                async with websockets.connect(self.relay_server) as ws:
                    self.ws = ws
                    self.is_connected = True
                    
                    # Регистрация агента
                    register_msg = {
                        "type": "register_agent",
                        "data": {
                            "computer_id": self.computer_id,
                            "session_id": self.session_id,
                            "session_token": self.session_token,
                            "agent_id": self.hostname,
                            "hostname": self.hostname
                        }
                    }
                    await ws.send(json.dumps(register_msg))
                    self.log_message.emit(f"✅ Зарегистрирован на сервере")
                    
                    self.connection_status_changed.emit(True, self.connected_clients)
                    
                    # Основной цикл приема команд
                    await self.receive_commands(ws)
                    
            except Exception as e:
                self.log_message.emit(f"❌ Ошибка подключения: {e}")
            
            self.is_connected = False
            self.connection_status_changed.emit(False, 0)
            
            if self.is_running:
                await asyncio.sleep(reconnect_delay)
        
        # Останавливаем задачи
        for task in tasks:
            task.cancel()
    
    async def send_system_info(self, ws):
        try:
            system_info = {
                "basic": SystemInfoCollector.get_basic_info(),
                "metrics": SystemInfoCollector.get_performance_metrics(),
                "timestamp": datetime.now().isoformat(),
                "computer_id": self.computer_id,
                "session_token": self.session_token
            }
            
            message = {
                "type": "system_info",
                "data": system_info,
                "computer_id": self.computer_id,
                "agent_id": self.hostname
            }
            
            await ws.send(json.dumps(message))
            return True
        except Exception as e:
            self.log_message.emit(f"Ошибка отправки system_info: {e}")
            return False
    
    async def screenshot_loop(self, ws):
        self.sending_screenshots = True
        
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
                        "computer_id": self.computer_id,
                        "agent_id": self.hostname
                    }
                    
                    await ws.send(json.dumps(message))
                
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
                
                if cmd_type == "register_client":
                    if client_id not in self.connected_clients_list:
                        self.connected_clients += 1
                        self.connected_clients_list.append(client_id)
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_connected.emit(client_id)
                        await self.send_system_info(ws)
                
                elif cmd_type == "start_stream":
                    self.streaming_clients.add(client_id)
                    if not self.sending_screenshots and len(self.streaming_clients) > 0:
                        asyncio.create_task(self.screenshot_loop(ws))
                
                elif cmd_type == "stop_stream":
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                
                elif cmd_type == "request_system_info":
                    await self.send_system_info(ws)
                
                elif cmd_type == "mouse_move":
                    await self.handle_mouse_move(data.get("data", {}))
                
                elif cmd_type == "mouse_click":
                    await self.handle_mouse_click(data.get("data", {}))
                
                elif cmd_type == "mouse_wheel":
                    await self.handle_mouse_wheel(data.get("data", {}))
                
                elif cmd_type == "keyboard_input":
                    await self.handle_keyboard_input(data.get("data", {}))
                
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
                await asyncio.sleep(0.01)
            
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
                else:
                    self.keyboard.type(text)
        except:
            pass
    
    def stop(self):
        self.log_message.emit("🛑 Остановка агента...")
        self.is_running = False
        self.is_connected = False
        self.streaming_clients.clear()
        self.connected_clients_list.clear()
        self.sending_screenshots = False
        
        DatabaseManager.update_computer_status(self.computer_id, False, self.session_id)
        self.log_message.emit(f"✅ Агент остановлен")


# ==================== ДИАЛОГ АВТОРИЗАЦИИ ====================
class AutoAuthDialog(QDialog):
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
            QDialog { background-color: white; border-radius: 10px; }
            QLabel { color: #333333; }
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
                        f"Логин: {computer_data['login']}\n"
                        f"Токен сессии: {computer_data.get('session_token', 'N/A')}\n\n"
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


# ==================== ДИАЛОГ НАСТРОЕК ====================
class SettingsDialog(QDialog):
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
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "RemoteAccessAgent", 0, winreg.REG_SZ, sys.executable + " " + __file__)
            winreg.CloseKey(key)
        except:
            pass
    
    def remove_from_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "RemoteAccessAgent")
            winreg.CloseKey(key)
        except:
            pass


# ==================== ГЛАВНОЕ ОКНО ====================
class RemoteAgentWindow(QMainWindow):
    def __init__(self, computer_data):
        super().__init__()
        self.computer_data = computer_data
        self.agent_thread = None
        self.tray_icon = None
        
        DatabaseManager.set_current_session(computer_data['computer_id'], computer_data['session_id'])
        
        self.init_ui()
        self.load_settings()
        
        if self.auto_reconnect:
            QTimer.singleShot(1000, self.connect_to_server)
        
        if self.minimize_to_tray:
            self.hide()
            self.create_tray_icon()
    
    def init_ui(self):
        self.setWindowTitle("Remote Access Agent")
        self.setGeometry(300, 300, 550, 450)
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
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
            QPushButton {
                background-color: #ff8c42;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff6b2c; }
            QLineEdit, QTextEdit {
                border: 1px solid #ff8c42;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        
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
                background-color: rgba(255,255,255,0.2);
                color: white;
                font-size: 20px;
                border-radius: 20px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.3); }
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(self.settings_btn)
        header_layout.setContentsMargins(10, 5, 15, 5)
        main_layout.addWidget(header_frame)
        
        info_group = QGroupBox("ИНФОРМАЦИЯ О СИСТЕМЕ")
        info_layout = QVBoxLayout()
        
        self.computer_label = QLabel()
        self.computer_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff8c42;")
        self.computer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.computer_label.setText(f"🖥️ {self.computer_data['hostname']}")
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
            QPushButton:hover { background-color: #c0392b; }
        """)
        self.exit_btn.clicked.connect(self.quit_application)
        exit_layout.addWidget(self.exit_btn)
        main_layout.addWidget(exit_frame)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")
    
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
        
        self.agent_thread.start()
    
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
    
    def quit_application(self):
        reply = QMessageBox.question(
            self, "Подтверждение", "Вы уверены, что хотите выйти?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(3000)
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            QApplication.quit()
    
    def closeEvent(self, event):
        if self.minimize_to_tray and self.tray_icon:
            event.ignore()
            self.hide()
        else:
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(3000)
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            event.accept()


# ==================== ТОЧКА ВХОДА ====================
def main():
    # Сначала создаем QApplication
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Remote Access Agent")
    
    # Проверяем права администратора
    if not is_admin():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Требуются права администратора")
        msg.setText("Для сбора событий из журнала Windows требуются права администратора.")
        msg.setInformativeText("Перезапустить программу с правами администратора?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            run_as_admin()
            sys.exit(0)
    
    auth_dialog = AutoAuthDialog()
    if auth_dialog.exec() == QDialog.DialogCode.Accepted:
        window = RemoteAgentWindow(auth_dialog.computer_data)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()