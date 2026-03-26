import json
import re
import threading
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict

from utils.constants import ANOMALY_THRESHOLDS


class JSONLogger:
    
    def __init__(self, temps_folder: str = None):
        if temps_folder is None:
            base_path = Path(__file__).parent.parent
            self.temps_folder = base_path / "temps"
        else:
            self.temps_folder = Path(temps_folder)
        
        self.temps_folder.mkdir(exist_ok=True)
        
        self.current_file = None
        self.current_date = None
        self.current_computer_name = None
        self.current_session_token = None
        self.lock = threading.Lock()
        
        self.previous_metrics = None
        self.anomaly_threshold = ANOMALY_THRESHOLDS
        
        # Служебная папка для маркеров
        self.markers_folder = self.temps_folder / ".markers"
        self.markers_folder.mkdir(exist_ok=True)
        
        # Файл флага - были ли уже записаны события за 24 часа
        self.events_flag_file = self.markers_folder / "events_24h_loaded.json"
        self._load_events_flag()
    
    def _load_events_flag(self):
        self._events_loaded_date = None
        if self.events_flag_file.exists():
            try:
                with open(self.events_flag_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._events_loaded_date = data.get('date')
            except:
                pass
    
    def _save_events_flag(self, date_str: str):
        try:
            with open(self.events_flag_file, 'w', encoding='utf-8') as f:
                json.dump({'date': date_str}, f)
        except:
            pass
    
    def _clear_events_flag(self):
        if self.events_flag_file.exists():
            try:
                self.events_flag_file.unlink()
            except:
                pass
        self._events_loaded_date = None
    
    def set_session(self, computer_name: str, session_token: str):
        self.current_computer_name = computer_name
        self.current_session_token = session_token
        
        old_date = self.current_date
        self.current_date = datetime.now().date()
        
        # Если день изменился, очищаем флаг
        if old_date is not None and old_date != self.current_date:
            self._clear_events_flag()
        else:
            # Если день не изменился, перезагружаем флаг
            self._load_events_flag()
        
        self.create_daily_file()
        self.check_and_mark_yesterday_file()
        self.cleanup_old_files()
    
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
        except Exception as e:
            print(f"Ошибка сохранения JSON файла: {e}")
    
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
    
    def add_metric(self, metrics: Dict):
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
        
        if self.previous_metrics:
            self.check_anomalies(metrics)
        
        self.previous_metrics = metrics.copy()
    
    def add_windows_events(self, events: List[Dict], is_initial: bool = False):
        records = self.load_records()
        
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
                        'message': event.get('message'),
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
                        'message': event.get('message', ''),
                        'category': event.get('category', 0),
                        'user': event.get('user', None)
                    }
                }
            records.append(record)
        
        self.save_records(records)
        
        if is_initial:
            self._save_events_flag(self.current_date.isoformat())
    
    def check_anomalies(self, current_metrics: Dict):
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
            self.mark_for_urgent_upload()
    
    def get_file_path_for_date(self, target_date: date) -> Path:
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.current_computer_name)
        return self.temps_folder / f"{clean_name}_{target_date.isoformat()}.json"
    
    def mark_for_urgent_upload(self):
        if self.current_file:
            marker_file = self.markers_folder / f"urgent_{self.current_file.name}"
            try:
                with open(marker_file, 'w') as f:
                    f.write(self.current_file.name)
            except:
                pass
    
    def mark_for_end_of_day_upload(self):
        if self.current_file:
            marker_file = self.markers_folder / f"endofday_{self.current_file.name}"
            try:
                with open(marker_file, 'w') as f:
                    f.write(self.current_file.name)
            except:
                pass
    
    def check_and_mark_yesterday_file(self) -> bool:
        yesterday = datetime.now().date() - timedelta(days=1)
        yesterday_file = self.get_file_path_for_date(yesterday)
        
        if yesterday_file.exists():
            sent_marker = self.markers_folder / f"sent_{yesterday_file.name}"
            if not sent_marker.exists():
                marker_file = self.markers_folder / f"endofday_{yesterday_file.name}"
                try:
                    with open(marker_file, 'w') as f:
                        f.write(yesterday_file.name)
                    return True
                except:
                    pass
        return False
    
    def mark_as_sent(self, file_name: str):
        sent_marker = self.markers_folder / f"sent_{file_name}"
        try:
            sent_marker.touch()
        except:
            pass
    
    def mark_today_as_sent(self):
        if self.current_file:
            self.mark_as_sent(self.current_file.name)
    
    def cleanup_old_files(self):
        """Удалить файлы старше 2 дней"""
        try:
            current_date = self.current_date
            files_to_keep = set()
            
            if self.current_file:
                files_to_keep.add(self.current_file.name)
            
            yesterday = current_date - timedelta(days=1)
            yesterday_file = self.get_file_path_for_date(yesterday)
            if yesterday_file.exists():
                files_to_keep.add(yesterday_file.name)
            
            for file_path in self.temps_folder.glob("*.json"):
                if file_path.name not in files_to_keep:
                    try:
                        file_path.unlink()
                    except:
                        pass
        except:
            pass
    
    def events_loaded_today(self) -> bool:
        return self._events_loaded_date == self.current_date.isoformat() if self.current_date else False
    
    def switch_to_new_day(self):
        self.mark_for_end_of_day_upload()
        self._clear_events_flag()
        self.current_date = datetime.now().date()
        self.create_daily_file()