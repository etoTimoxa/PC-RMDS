import json
import re
import threading
import sys
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict

from utils.constants import ANOMALY_THRESHOLDS
from utils.platform_utils import get_data_dir, ensure_dirs


class JSONLogger:
    
    def __init__(self, temps_folder: str = None):
        if temps_folder is None:
            # Используем platform_utils для определения правильной директории
            # Windows: %APPDATA%/RemoteAccessAgent/temps/
            # Linux: ~/.local/share/RemoteAccessAgent/temps/
            ensure_dirs()  # Создаем все необходимые директории
            self.temps_folder = get_data_dir() / "temps"
        else:
            self.temps_folder = Path(temps_folder)
        
        self.temps_folder.mkdir(parents=True, exist_ok=True)
        
        self.current_file = None
        self.current_date = None
        self.current_computer_name = None
        self.current_session_token = None
        self.lock = threading.Lock()
        
        self.previous_metrics = None
        self.anomaly_threshold = ANOMALY_THRESHOLDS
        
        self.markers_folder = self.temps_folder / ".markers"
        self.markers_folder.mkdir(parents=True, exist_ok=True)
        
        self.events_info_file = self.markers_folder / "events_collection_info.json"
        self._load_events_info()
        
        # Флаг для отслеживания, был ли файл отправлен срочно
        self.urgent_sent = False
        self.last_urgent_upload_time = None  # Время последней срочной отправки
    
    def _load_events_info(self):
        self._last_collection_time = None
        if self.events_info_file.exists():
            try:
                with open(self.events_info_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('date') == self.current_date.isoformat() if self.current_date else None:
                        last_time_str = data.get('last_collection_time')
                        if last_time_str:
                            self._last_collection_time = datetime.fromisoformat(last_time_str)
            except:
                pass
    
    def _save_events_info(self, last_collection_time: datetime):
        if self.current_date:
            try:
                with open(self.events_info_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'date': self.current_date.isoformat(),
                        'last_collection_time': last_collection_time.isoformat() if last_collection_time else None
                    }, f)
            except:
                pass
    
    def _clear_events_info(self):
        self._last_collection_time = None
        if self.events_info_file.exists():
            try:
                self.events_info_file.unlink()
            except:
                pass
    
    def set_session(self, computer_name: str, session_token: str):
        self.current_computer_name = computer_name
        self.current_session_token = session_token
        
        old_date = self.current_date
        self.current_date = datetime.now().date()
        
        if old_date is not None and old_date != self.current_date:
            self._clear_events_info()
        else:
            self._load_events_info()
        
        self.create_daily_file()
        self.mark_all_unsent_files()
        self.cleanup_old_files()
        
        # Сбрасываем флаг срочной отправки при смене дня
        self.urgent_sent = False
    
    def create_daily_file(self):
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.current_computer_name)
        file_name = f"{clean_name}_{self.current_date.isoformat()}.json"
        self.current_file = self.temps_folder / file_name
        
        if not self.current_file.exists():
            self.save_records([])
    
    def save_records(self, records: List[Dict]):
        if not self.current_file:
            return
        
        try:
            with self.lock:
                with open(self.current_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def load_records(self) -> List[Dict]:
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
    
    def add_metric(self, metrics: Dict, force_write: bool = False):
        """Добавляет метрику в файл.
        
        Args:
            metrics: Словарь с метриками
            force_write: Если True, принудительно записывает в файл (при скачках)
        """
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
        
        # Проверяем аномалии
        anomaly_detected = False
        if self.previous_metrics:
            anomaly_detected = self.check_anomalies(metrics)
        
        self.previous_metrics = metrics.copy()
        
        # Если обнаружена аномалия, помечаем для срочной отправки
        if anomaly_detected and self.should_mark_urgent():
            self.mark_for_urgent_upload()
            self.urgent_sent = True
        
        # Если принудительная запись (скачок) - сразу помечаем для отправки
        if force_write and anomaly_detected:
            self.mark_for_urgent_upload()
            self.urgent_sent = True
    
    def force_write_metric(self, metrics: Dict):
        """Принудительно записывает метрику при обнаружении скачка.
        Используется для немедленной записи важных событий.
        """
        self.add_metric(metrics, force_write=True)
    
    def add_windows_events(self, events: List[Dict], is_initial: bool = False):
        records = self.load_records()
        MAX_RECORDS = 2000
        
        for event in events:
            if event.get('is_grouped'):
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
                        'message': event.get('message')[:300] if event.get('message') else '',
                        'category': event.get('category'),
                        'user': event.get('user')
                    }
                }
            else:
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
                        'message': event.get('message', '')[:300],
                        'category': event.get('category', 0),
                        'user': event.get('user', None)
                    }
                }
            records.append(record)
        
        if len(records) > MAX_RECORDS:
            records = records[-MAX_RECORDS:]
        
        self.save_records(records)
        
        if is_initial:
            collection_time = datetime.now()
            self._last_collection_time = collection_time
            self._save_events_info(collection_time)
    
    def check_anomalies(self, current_metrics: Dict) -> bool:
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
            records = self.load_records()
            records.append({
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
            })
            self.save_records(records)
            return True
        return False
    
    def get_file_path_for_date(self, target_date: date) -> Path:
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.current_computer_name)
        return self.temps_folder / f"{clean_name}_{target_date.isoformat()}.json"
    
    def mark_for_urgent_upload(self):
        """Помечает текущий файл для срочной отправки (не создавая копию)"""
        if self.current_file:
            # Сбрасываем флаг, чтобы следующий скачок мог снова триггерить отправку
            self.urgent_sent = False
            marker_file = self.markers_folder / f"urgent_{self.current_file.name}"
            try:
                with open(marker_file, 'w') as f:
                    f.write(self.current_file.name)
            except:
                pass
    
    def reset_urgent_flag(self):
        """Сбрасывает флаг срочной отправки после успешной загрузки"""
        self.urgent_sent = False
        self.last_urgent_upload_time = datetime.now()
    
    def should_mark_urgent(self) -> bool:
        """Проверяет, нужно ли помечать файл для срочной отправки"""
        # Если флаг уже установлен, не помечаем снова
        if self.urgent_sent:
            return False
        # Если последняя отправка была менее 30 секунд назад, не помечаем
        if self.last_urgent_upload_time:
            time_since_last = (datetime.now() - self.last_urgent_upload_time).total_seconds()
            if time_since_last < 30:
                return False
        return True
    
    def mark_for_end_of_day_upload(self, file_name: str = None):
        """Помечает файл для отправки в конце дня"""
        if file_name is None and self.current_file:
            file_name = self.current_file.name
        
        if file_name:
            marker_file = self.markers_folder / f"endofday_{file_name}"
            try:
                with open(marker_file, 'w') as f:
                    f.write(file_name)
            except:
                pass
    
    def mark_all_unsent_files(self):
        """Помечает все файлы за предыдущие дни, которых нет в облаке"""
        current_date = self.current_date
        files_marked = 0
        
        # Получаем список уже отправленных файлов
        sent_files = set()
        for sent_marker in self.markers_folder.glob("sent_*.json"):
            sent_files.add(sent_marker.name.replace("sent_", ""))
        
        for file_path in self.temps_folder.glob("*.json"):
            if file_path.name.startswith('.'):
                continue
            
            # Если файл уже отправлен, пропускаем
            if file_path.name in sent_files:
                continue
            
            try:
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})\.json$', file_path.name)
                if not date_match:
                    continue
                
                file_date_str = date_match.group(1)
                file_date = datetime.fromisoformat(file_date_str).date()
                
                # Все файлы за предыдущие дни помечаем для отправки
                if file_date < current_date:
                    self.mark_for_end_of_day_upload(file_path.name)
                    files_marked += 1
            except Exception:
                pass
    
    def check_and_mark_yesterday_file(self) -> bool:
        """Проверяет файл за вчерашний день и помечает его для отправки"""
        yesterday = datetime.now().date() - timedelta(days=1)
        yesterday_file = self.get_file_path_for_date(yesterday)
        
        if yesterday_file.exists():
            sent_marker = self.markers_folder / f"sent_{yesterday_file.name}"
            # Если не отправлен и не помечен как отправленный
            if not sent_marker.exists():
                # Проверяем, не помечен ли уже
                endofday_marker = self.markers_folder / f"endofday_{yesterday_file.name}"
                if not endofday_marker.exists():
                    self.mark_for_end_of_day_upload(yesterday_file.name)
                    return True
        return False
    
    def mark_as_sent(self, file_name: str):
        """Помечает файл как отправленный"""
        sent_marker = self.markers_folder / f"sent_{file_name}"
        try:
            sent_marker.touch()
        except:
            pass
    
    def mark_today_as_sent(self):
        if self.current_file:
            self.mark_as_sent(self.current_file.name)
    
    def cleanup_old_files(self):
        """Очищает старые файлы, оставляя только текущий и вчерашний"""
        try:
            current_date = self.current_date
            files_to_keep = set()
            
            if self.current_file:
                files_to_keep.add(self.current_file.name)
            
            yesterday = current_date - timedelta(days=1)
            yesterday_file = self.get_file_path_for_date(yesterday)
            if yesterday_file.exists():
                files_to_keep.add(yesterday_file.name)
            
            # Проверяем, есть ли файлы с отправленными маркерами
            sent_markers = list(self.markers_folder.glob("sent_*.json"))
            for marker in sent_markers:
                file_name = marker.name.replace("sent_", "")
                if file_name not in files_to_keep:
                    file_path = self.temps_folder / file_name
                    if file_path.exists():
                        # Оставляем отправленные файлы на 7 дней
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})\.json$', file_name)
                        if date_match:
                            file_date_str = date_match.group(1)
                            file_date = datetime.fromisoformat(file_date_str).date()
                            if (current_date - file_date).days <= 7:
                                files_to_keep.add(file_name)
            
            for file_path in self.temps_folder.glob("*.json"):
                if file_path.name not in files_to_keep:
                    try:
                        file_path.unlink()
                    except:
                        pass
        except Exception:
            pass
    
    def should_collect_events(self) -> bool:
        if self._last_collection_time is None:
            return True
        minutes_since_last = (datetime.now() - self._last_collection_time).total_seconds() / 60
        return minutes_since_last >= 30
    
    def get_last_collection_time(self) -> datetime:
        return self._last_collection_time
    
    def switch_to_new_day(self):
        """Переключение на новый день"""
        old_file_name = self.current_file.name if self.current_file else None
        old_file_path = self.current_file if self.current_file else None
        
        if old_file_path and old_file_path.exists():
            records = self.load_records()
            if records:
                # Если есть записи, помечаем для отправки
                self.mark_for_end_of_day_upload(old_file_name)
            else:
                # Если файл пустой, удаляем
                try:
                    old_file_path.unlink()
                except:
                    pass
        
        self._clear_events_info()
        self.current_date = datetime.now().date()
        self.urgent_sent = False  # Сбрасываем флаг срочной отправки
        self.create_daily_file()