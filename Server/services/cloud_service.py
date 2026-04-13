"""
Cloud Service - работа с облачным хранилищем (S3)
"""
import json
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any, Generator
from pathlib import Path
import re
import io

from config import CLOUD_CONFIG, METRICS_CONFIG


class CloudService:
    """Сервис для работы с S3 облачным хранилищем"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config = CLOUD_CONFIG
        self._s3 = None
        self._bucket_name = self._config['bucket_name']
        self._init_s3()
    
    def _init_s3(self):
        """Инициализация S3 клиента"""
        try:
            self._s3 = boto3.client(
                's3',
                endpoint_url=self._config['endpoint_url'],
                aws_access_key_id=self._config['access_key'],
                aws_secret_access_key=self._config['secret_key'],
                config=Config(
                    signature_version='s3v4',
                    retries={'max_attempts': 3, 'mode': 'standard'}
                )
            )
        except Exception as e:
            print(f"Ошибка инициализации S3: {e}")
            self._s3 = None
    
    def _sanitize_hostname(self, hostname: str) -> str:
        """Санитизировать hostname для использования в имени файла"""
        return re.sub(r'[^a-zA-Z0-9_-]', '_', hostname)
    
    def list_metric_files(
        self,
        hostname: str,
        from_date: date,
        to_date: date
    ) -> List[str]:
        """Получить список файлов метрик для компьютера за период"""
        if not self._s3:
            return []
        
        sanitized_name = self._sanitize_hostname(hostname)
        prefix = sanitized_name
        
        files = []
        try:
            paginator = self._s3.get_paginator('list_objects_v2')
            
            # Генерируем все даты в диапазоне
            current_date = from_date
            while current_date <= to_date:
                file_key = f"{sanitized_name}_{current_date.isoformat()}.json"
                try:
                    # Проверяем существование файла
                    self._s3.head_object(Bucket=self._bucket_name, Key=file_key)
                    files.append(file_key)
                except ClientError as e:
                    if e.response['Error']['Code'] != '404':
                        print(f"Ошибка проверки файла {file_key}: {e}")
                
                current_date += timedelta(days=1)
            
            return files
            
        except Exception as e:
            print(f"Ошибка при получении списка файлов: {e}")
            return []
    
    def read_metrics_chunked(
        self,
        file_key: str,
        from_timestamp: datetime = None,
        to_timestamp: datetime = None,
        max_records: int = None
    ) -> List[Dict]:
        """
        Читать метрики из файла с фильтрацией по времени.
        
        Args:
            file_key: Ключ файла в S3
            from_timestamp: Начало периода
            to_timestamp: Конец периода
            max_records: Максимальное количество записей
            
        Returns:
            Список записей метрик
        """
        if not self._s3:
            return []
        
        if max_records is None:
            max_records = METRICS_CONFIG['max_points_per_request']
        
        records = []
        
        try:
            # Получаем объект из S3
            response = self._s3.get_object(Bucket=self._bucket_name, Key=file_key)
            content = response['Body'].read().decode('utf-8')
            
            # Парсим JSON
            try:
                data = json.loads(content)
                if not isinstance(data, list):
                    data = [data]
            except json.JSONDecodeError:
                # Возможно файл в формате JSONL (одна запись на строку)
                data = []
                for line in content.strip().split('\n'):
                    if line.strip():
                        try:
                            data.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            
            # Фильтруем по времени
            for record in data:
                timestamp_str = record.get('timestamp')
                if not timestamp_str:
                    # Пропускаем записи без timestamp (например, grouped events)
                    if record.get('type') in ['windows_event_grouped', 'user_action']:
                        records.append(record)
                    continue
                
                try:
                    record_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    continue
                
                # Фильтрация по времени
                if from_timestamp and record_time < from_timestamp:
                    continue
                if to_timestamp and record_time > to_timestamp:
                    continue
                
                # Берем только метрики
                if record.get('type') == 'metric':
                    records.append(record)
                
                if len(records) >= max_records:
                    break
            
            return records
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return []
            print(f"Ошибка чтения файла {file_key}: {e}")
            return []
        except Exception as e:
            print(f"Общая ошибка при чтении {file_key}: {e}")
            return []
    
    def read_events_chunked(
        self,
        file_key: str,
        from_timestamp: datetime = None,
        to_timestamp: datetime = None,
        event_type: str = 'all',
        max_records: int = None
    ) -> List[Dict]:
        """
        Читать события из файла с фильтрацией.
        
        Args:
            file_key: Ключ файла в S3
            from_timestamp: Начало периода
            to_timestamp: Конец периода
            event_type: Тип событий (windows_event, user_action, all)
            max_records: Максимальное количество записей
        """
        if not self._s3:
            return []
        
        if max_records is None:
            max_records = METRICS_CONFIG['max_points_per_request']
        
        records = []
        
        try:
            response = self._s3.get_object(Bucket=self._bucket_name, Key=file_key)
            content = response['Body'].read().decode('utf-8')
            
            # Парсим JSON
            try:
                data = json.loads(content)
                if not isinstance(data, list):
                    data = [data]
            except json.JSONDecodeError:
                data = []
                for line in content.strip().split('\n'):
                    if line.strip():
                        try:
                            data.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            
            # Фильтруем события
            for record in data:
                record_type = record.get('type', '')
                
                # Фильтруем по типу
                if event_type == 'windows_event':
                    if record_type not in ['windows_event', 'windows_event_grouped']:
                        continue
                elif event_type == 'user_action':
                    if record_type != 'user_action':
                        continue
                elif event_type != 'all':
                    if record_type != event_type:
                        continue
                
                # Фильтруем по времени
                timestamp_str = record.get('timestamp') or record.get('data', {}).get('timestamp')
                if timestamp_str:
                    try:
                        record_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if from_timestamp and record_time < from_timestamp:
                            continue
                        if to_timestamp and record_time > to_timestamp:
                            continue
                    except (ValueError, AttributeError):
                        pass
                
                records.append(record)
                
                if len(records) >= max_records:
                    break
            
            return records
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return []
            print(f"Ошибка чтения файла {file_key}: {e}")
            return []
        except Exception as e:
            print(f"Общая ошибка при чтении {file_key}: {e}")
            return []
    
    def get_metrics(
        self,
        hostname: str,
        from_date: datetime,
        to_date: datetime,
        metric_type: str = 'all',
        resolution: str = 'raw',
        limit: int = None
    ) -> Dict:
        """
        Получить метрики за период.
        
        Args:
            hostname: Hostname компьютера
            from_date: Начало периода
            to_date: Конец периода
            metric_type: Тип метрик (cpu, ram, disk, network, all)
            resolution: Разрешение (raw, 5min, 30min)
            limit: Максимум точек
        """
        if limit is None:
            limit = METRICS_CONFIG['max_points_per_request']
        
        # Определяем даты
        from_date_date = from_date.date() if isinstance(from_date, datetime) else from_date
        to_date_date = to_date.date() if isinstance(to_date, datetime) else to_date
        
        # Получаем список файлов
        files = self.list_metric_files(hostname, from_date_date, to_date_date)
        
        all_metrics = []
        files_processed = 0
        
        for file_key in files:
            metrics = self.read_metrics_chunked(
                file_key,
                from_timestamp=from_date,
                to_timestamp=to_date,
                max_records=limit // len(files) if files else limit
            )
            all_metrics.extend(metrics)
            files_processed += 1
            
            if len(all_metrics) >= limit:
                break
        
        # Сортируем по времени
        all_metrics.sort(key=lambda x: x.get('timestamp', ''))
        
        # Ограничиваем количество
        if len(all_metrics) > limit:
            all_metrics = all_metrics[:limit]
        
        # Агрегация по разрешению
        if resolution != 'raw':
            all_metrics = self._aggregate_metrics(all_metrics, resolution)
        
        # Формируем результат
        result_metrics = []
        for m in all_metrics:
            data = m.get('data', {})
            entry = {
                'timestamp': m.get('timestamp'),
                'computer_name': m.get('computer_name'),
                'type': m.get('type')
            }
            
            if metric_type in ['all', 'cpu']:
                entry['cpu_usage'] = data.get('cpu_usage')
            
            if metric_type in ['all', 'ram']:
                entry['ram_usage'] = data.get('ram_usage')
                entry['ram_used_gb'] = data.get('ram_used_gb')
                entry['ram_total_gb'] = data.get('ram_total_gb')
            
            if metric_type in ['all', 'disk']:
                entry['disk_usage'] = data.get('disk_usage')
                entry['disk_used_gb'] = data.get('disk_used_gb')
                entry['disk_total_gb'] = data.get('disk_total_gb')
            
            if metric_type in ['all', 'network']:
                entry['network_sent_mb'] = data.get('network_sent_mb')
                entry['network_recv_mb'] = data.get('network_recv_mb')
            
            result_metrics.append(entry)
        
        return {
            'hostname': hostname,
            'from': from_date.isoformat() if isinstance(from_date, datetime) else str(from_date),
            'to': to_date.isoformat() if isinstance(to_date, datetime) else str(to_date),
            'resolution': resolution,
            'metric_type': metric_type,
            'points_count': len(result_metrics),
            'files_processed': files_processed,
            'metrics': result_metrics
        }
    
    def get_events(
        self,
        hostname: str,
        from_date: datetime = None,
        to_date: datetime = None,
        event_type: str = 'all',
        limit: int = 100
    ) -> Dict:
        """
        Получить события за период.
        """
        if from_date is None:
            from_date = datetime.now() - timedelta(days=7)
        if to_date is None:
            to_date = datetime.now()
        
        from_date_date = from_date.date() if isinstance(from_date, datetime) else from_date
        to_date_date = to_date.date() if isinstance(to_date, datetime) else to_date
        
        # Получаем список файлов
        files = self.list_metric_files(hostname, from_date_date, to_date_date)
        
        all_events = []
        files_processed = 0
        
        for file_key in files:
            events = self.read_events_chunked(
                file_key,
                from_timestamp=from_date,
                to_timestamp=to_date,
                event_type=event_type,
                max_records=limit // len(files) if files else limit
            )
            all_events.extend(events)
            files_processed += 1
            
            if len(all_events) >= limit:
                break
        
        # Сортируем по времени (новые первые)
        all_events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Ограничиваем
        if len(all_events) > limit:
            all_events = all_events[:limit]
        
        return {
            'hostname': hostname,
            'from': from_date.isoformat() if isinstance(from_date, datetime) else str(from_date),
            'to': to_date.isoformat() if isinstance(to_date, datetime) else str(to_date),
            'event_type': event_type,
            'total': len(all_events),
            'files_processed': files_processed,
            'events': all_events
        }
    
    def get_summary(
        self,
        hostname: str,
        from_date: datetime = None,
        to_date: datetime = None,
        period: str = 'day'
    ) -> Dict:
        """
        Получить агрегированную статистику.
        """
        if from_date is None:
            if period == 'hour':
                from_date = datetime.now() - timedelta(hours=1)
            elif period == 'day':
                from_date = datetime.now() - timedelta(days=1)
            elif period == 'week':
                from_date = datetime.now() - timedelta(weeks=1)
            else:
                from_date = datetime.now() - timedelta(days=1)
        
        if to_date is None:
            to_date = datetime.now()
        
        # Получаем метрики
        metrics_data = self.get_metrics(
            hostname,
            from_date,
            to_date,
            metric_type='all',
            resolution='raw',
            limit=5000
        )
        
        metrics = metrics_data.get('metrics', [])
        
        if not metrics:
            return {
                'hostname': hostname,
                'period': period,
                'from': from_date.isoformat(),
                'to': to_date.isoformat(),
                'metrics_count': 0,
                'summary': {
                    'cpu': {'avg': None, 'max': None, 'min': None},
                    'ram': {'avg': None, 'max': None, 'min': None},
                    'disk': {'avg': None, 'max': None, 'min': None},
                    'network': {'avg_sent': None, 'avg_recv': None}
                },
                'uptime_percentage': None,
                'event_count': 0
            }
        
        # Вычисляем статистику
        cpu_values = [m['cpu_usage'] for m in metrics if m.get('cpu_usage') is not None]
        ram_values = [m['ram_usage'] for m in metrics if m.get('ram_usage') is not None]
        disk_values = [m['disk_usage'] for m in metrics if m.get('disk_usage') is not None]
        network_sent = [m['network_sent_mb'] for m in metrics if m.get('network_sent_mb') is not None]
        network_recv = [m['network_recv_mb'] for m in metrics if m.get('network_recv_mb') is not None]
        
        def calc_stats(values):
            if not values:
                return {'avg': None, 'max': None, 'min': None}
            return {
                'avg': round(sum(values) / len(values), 2),
                'max': round(max(values), 2),
                'min': round(min(values), 2)
            }
        
        def calc_avg(values):
            if not values:
                return None
            return round(sum(values) / len(values), 2)
        
        # Получаем события
        events_data = self.get_events(hostname, from_date, to_date, limit=10000)
        event_count = events_data.get('total', 0)
        
        # Вычисляем uptime (считаем что если были метрики - компьютер был онлайн)
        total_minutes = (to_date - from_date).total_seconds() / 60
        uptime_percentage = round((len(metrics) * 30) / total_minutes * 100, 2) if total_minutes > 0 else 0
        uptime_percentage = min(100, uptime_percentage)  # Не больше 100%
        
        return {
            'hostname': hostname,
            'period': period,
            'from': from_date.isoformat(),
            'to': to_date.isoformat(),
            'metrics_count': len(metrics),
            'summary': {
                'cpu': calc_stats(cpu_values),
                'ram': calc_stats(ram_values),
                'disk': calc_stats(disk_values),
                'network': {
                    'avg_sent_mb': calc_avg(network_sent),
                    'avg_recv_mb': calc_avg(network_recv),
                    'total_sent_mb': round(sum(network_sent), 2) if network_sent else None,
                    'total_recv_mb': round(sum(network_recv), 2) if network_recv else None
                }
            },
            'uptime_percentage': uptime_percentage,
            'event_count': event_count
        }
    
    def get_sessions(
        self,
        hostname: str,
        from_date: date = None,
        to_date: date = None
    ) -> Dict:
        """
        Получить список сессий за период.
        
        Args:
            hostname: Hostname компьютера
            from_date: Начало периода
            to_date: Конец периода
        """
        if from_date is None:
            from_date = date.today()
        if to_date is None:
            to_date = date.today()
        
        # Получаем файлы
        files = self.list_metric_files(hostname, from_date, to_date)
        
        sessions = {}
        
        for file_key in files:
            records = self.read_all_records(file_key)
            
            for record in records:
                session_token = record.get('session_token')
                if not session_token:
                    continue
                
                if session_token not in sessions:
                    sessions[session_token] = {
                        'session_token': session_token,
                        'hostname': hostname,
                        'record_count': 0,
                        'metric_count': 0,
                        'event_count': 0,
                        'first_timestamp': None,
                        'last_timestamp': None
                    }
                
                ts = record.get('timestamp', '')
                rec_type = record.get('type', '')
                
                sessions[session_token]['record_count'] += 1
                
                if rec_type == 'metric':
                    sessions[session_token]['metric_count'] += 1
                elif rec_type in ['windows_event', 'windows_event_grouped', 'user_action']:
                    sessions[session_token]['event_count'] += 1
                
                if ts:
                    if not sessions[session_token]['first_timestamp']:
                        sessions[session_token]['first_timestamp'] = ts
                    sessions[session_token]['last_timestamp'] = ts
        
        # Сортируем по времени (новые первые)
        result = sorted(sessions.values(), key=lambda x: x.get('first_timestamp', ''), reverse=True)
        
        return {
            'hostname': hostname,
            'from': str(from_date),
            'to': str(to_date),
            'total_sessions': len(result),
            'sessions': result
        }
    
    def get_session_metrics(
        self,
        hostname: str,
        session_token: str,
        metric_type: str = 'all',
        limit: int = None
    ) -> Dict:
        """
        Получить метрики конкретной сессии.
        
        Args:
            hostname: Hostname компьютера
            session_token: Токен сессии
            metric_type: Тип метрик (cpu, ram, disk, network, all)
            limit: Максимум записей
        """
        if limit is None:
            limit = METRICS_CONFIG['max_points_per_request']
        
        # Получаем все файлы за период (session_token содержит дату)
        # Формат: hostname_date_time
        parts = session_token.split('_')
        if len(parts) >= 3:
            session_date_str = parts[1]  # YYYY-MM-DD
        else:
            session_date_str = date.today().isoformat()
        
        try:
            session_date = date.fromisoformat(session_date_str)
        except ValueError:
            session_date = date.today()
        
        files = self.list_metric_files(hostname, session_date, session_date)
        
        metrics = []
        
        for file_key in files:
            records = self.read_all_records(file_key)
            
            for record in records:
                if record.get('session_token') != session_token:
                    continue
                if record.get('type') != 'metric':
                    continue
                
                data = record.get('data', {})
                entry = {
                    'timestamp': record.get('timestamp'),
                    'session_token': session_token,
                    'type': 'metric'
                }
                
                if metric_type in ['all', 'cpu']:
                    entry['cpu_usage'] = data.get('cpu_usage')
                
                if metric_type in ['all', 'ram']:
                    entry['ram_usage'] = data.get('ram_usage')
                    entry['ram_used_gb'] = data.get('ram_used_gb')
                    entry['ram_total_gb'] = data.get('ram_total_gb')
                
                if metric_type in ['all', 'disk']:
                    entry['disk_usage'] = data.get('disk_usage')
                    entry['disk_used_gb'] = data.get('disk_used_gb')
                    entry['disk_total_gb'] = data.get('disk_total_gb')
                
                if metric_type in ['all', 'network']:
                    entry['network_sent_mb'] = data.get('network_sent_mb')
                    entry['network_recv_mb'] = data.get('network_recv_mb')
                
                metrics.append(entry)
                
                if len(metrics) >= limit:
                    break
        
        # Сортируем по времени
        metrics.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            'hostname': hostname,
            'session_token': session_token,
            'metric_type': metric_type,
            'count': len(metrics),
            'metrics': metrics
        }
    
    def get_session_events(
        self,
        hostname: str,
        session_token: str,
        event_type: str = 'all',
        limit: int = 100
    ) -> Dict:
        """
        Получить события конкретной сессии.
        
        Args:
            hostname: Hostname компьютера
            session_token: Токен сессии
            event_type: Тип событий (windows_event, user_action, all)
            limit: Максимум записей
        """
        # Получаем дату сессии
        parts = session_token.split('_')
        if len(parts) >= 3:
            session_date_str = parts[1]
        else:
            session_date_str = date.today().isoformat()
        
        try:
            session_date = date.fromisoformat(session_date_str)
        except ValueError:
            session_date = date.today()
        
        files = self.list_metric_files(hostname, session_date, session_date)
        
        events = []
        
        for file_key in files:
            records = self.read_all_records(file_key)
            
            for record in records:
                if record.get('session_token') != session_token:
                    continue
                
                rec_type = record.get('type', '')
                
                # Фильтруем по типу
                if event_type == 'windows_event':
                    if rec_type not in ['windows_event', 'windows_event_grouped']:
                        continue
                elif event_type == 'user_action':
                    if rec_type != 'user_action':
                        continue
                elif event_type != 'all':
                    if rec_type != event_type:
                        continue
                
                events.append(record)
                
                if len(events) >= limit:
                    break
        
        # Сортируем по времени (новые первые)
        events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return {
            'hostname': hostname,
            'session_token': session_token,
            'event_type': event_type,
            'count': len(events),
            'events': events
        }
    
    def read_all_records(self, file_key: str) -> List[Dict]:
        """
        Читать все записи из файла (без фильтрации).
        
        Args:
            file_key: Ключ файла в S3
            
        Returns:
            Список всех записей
        """
        if not self._s3:
            return []
        
        try:
            response = self._s3.get_object(Bucket=self._bucket_name, Key=file_key)
            content = response['Body'].read().decode('utf-8')
            
            data = json.loads(content)
            if not isinstance(data, list):
                data = [data]
            
            return data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return []
            print(f"Ошибка чтения файла {file_key}: {e}")
            return []
        except Exception as e:
            print(f"Общая ошибка при чтении {file_key}: {e}")
            return []
    
    def _aggregate_metrics(self, metrics: List[Dict], resolution: str) -> List[Dict]:
        """
        Агрегация метрик до нужного разрешения.
        
        Args:
            metrics: Список метрик
            resolution: Разрешение (5min, 30min)
        """
        if not metrics or resolution == 'raw':
            return metrics
        
        # Определяем размер окна в минутах
        window_minutes = 5 if resolution == '5min' else 30
        
        # Группируем по временным окнам
        buckets = {}
        
        for m in metrics:
            ts_str = m.get('timestamp')
            if not ts_str:
                continue
            
            try:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                continue
            
            # Округляем до начала окна
            minutes = (ts.minute // window_minutes) * window_minutes
            bucket_key = ts.replace(minute=minutes, second=0, microsecond=0)
            
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(m)
        
        # Агрегируем каждое окно
        result = []
        
        for bucket_time in sorted(buckets.keys()):
            bucket_metrics = buckets[bucket_time]
            
            if not bucket_metrics:
                continue
            
            # Усредняем все значения
            data = bucket_metrics[0].get('data', {})
            
            cpu_values = [m.get('data', {}).get('cpu_usage') for m in bucket_metrics 
                         if m.get('data', {}).get('cpu_usage') is not None]
            ram_values = [m.get('data', {}).get('ram_usage') for m in bucket_metrics 
                         if m.get('data', {}).get('ram_usage') is not None]
            disk_values = [m.get('data', {}).get('disk_usage') for m in bucket_metrics 
                          if m.get('data', {}).get('disk_usage') is not None]
            
            result.append({
                'timestamp': bucket_time.isoformat(),
                'computer_name': bucket_metrics[0].get('computer_name'),
                'type': 'metric',
                'data': {
                    'cpu_usage': round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else None,
                    'ram_usage': round(sum(ram_values) / len(ram_values), 2) if ram_values else None,
                    'ram_used_gb': bucket_metrics[-1].get('data', {}).get('ram_used_gb'),
                    'ram_total_gb': bucket_metrics[-1].get('data', {}).get('ram_total_gb'),
                    'disk_usage': round(sum(disk_values) / len(disk_values), 2) if disk_values else None,
                    'disk_used_gb': bucket_metrics[-1].get('data', {}).get('disk_used_gb'),
                    'disk_total_gb': bucket_metrics[-1].get('data', {}).get('disk_total_gb'),
                    'network_sent_mb': bucket_metrics[-1].get('data', {}).get('network_sent_mb'),
                    'network_recv_mb': bucket_metrics[-1].get('data', {}).get('network_recv_mb'),
                }
            })
        
        return result
    
    def file_exists(self, file_key: str) -> bool:
        """Проверяет существование файла в облаке"""
        if not self._s3:
            return False
        
        try:
            self._s3.head_object(Bucket=self._bucket_name, Key=file_key)
            return True
        except ClientError:
            return False
    
    def get_file_info(self, file_key: str) -> Optional[Dict]:
        """Получить информацию о файле"""
        if not self._s3:
            return None
        
        try:
            response = self._s3.head_object(Bucket=self._bucket_name, Key=file_key)
            return {
                'key': file_key,
                'size': response.get('ContentLength'),
                'last_modified': response.get('LastModified').isoformat() if response.get('LastModified') else None,
                'content_type': response.get('ContentType')
            }
        except ClientError:
            return None

    def get_full_day_file(self, hostname: str, date_str: str) -> Dict:
        """
        Получить полное содержимое файла за указанный день целиком.
        
        Args:
            hostname: Название компьютера
            date_str: Дата в формате YYYY-MM-DD
            
        Returns:
            Полное содержимое файла со всеми записями
        """
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return {
                'success': False,
                'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD',
                'hostname': hostname,
                'date': date_str,
                'records': []
            }
        
        sanitized_name = self._sanitize_hostname(hostname)
        file_key = f"{sanitized_name}_{target_date.isoformat()}.json"
        
        if not self.file_exists(file_key):
            return {
                'success': False,
                'error': 'Файл не найден в облаке',
                'hostname': hostname,
                'date': date_str,
                'file_key': file_key,
                'records': []
            }
        
        records = self.read_all_records(file_key)
        file_info = self.get_file_info(file_key)
        
        return {
            'success': True,
            'hostname': hostname,
            'date': date_str,
            'file_key': file_key,
            'file_info': file_info,
            'records_count': len(records),
            'records': records
        }

    def get_full_period_files(self, hostname: str, from_date_str: str, to_date_str: str) -> Dict:
        """
        Получить все записи из файлов за указанный период (несколько дней).
        
        Args:
            hostname: Название компьютера
            from_date_str: Начальная дата в формате YYYY-MM-DD
            to_date_str: Конечная дата в формате YYYY-MM-DD
            
        Returns:
            Все записи со всех дневных файлов за период
        """
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            return {
                'success': False,
                'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD',
                'hostname': hostname,
                'from_date': from_date_str,
                'to_date': to_date_str,
                'files_found': 0,
                'records_count': 0,
                'records': []
            }
        
        if from_date > to_date:
            return {
                'success': False,
                'error': 'Начальная дата не может быть больше конечной',
                'hostname': hostname,
                'from_date': from_date_str,
                'to_date': to_date_str,
                'files_found': 0,
                'records_count': 0,
                'records': []
            }
        
        sanitized_name = self._sanitize_hostname(hostname)
        all_records = []
        found_files = []
        current_date = from_date
        
        while current_date <= to_date:
            file_key = f"{sanitized_name}_{current_date.isoformat()}.json"
            
            if self.file_exists(file_key):
                file_records = self.read_all_records(file_key)
                all_records.extend(file_records)
                found_files.append({
                    'date': current_date.isoformat(),
                    'file_key': file_key,
                    'records_count': len(file_records)
                })
            
            current_date += timedelta(days=1)
        
        # Сортируем все записи по времени
        all_records.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            'success': True,
            'hostname': hostname,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'days_total': (to_date - from_date).days + 1,
            'files_found': len(found_files),
            'files': found_files,
            'records_count': len(all_records),
            'records': all_records
        }

    def upload_metrics_file(self, file) -> Dict:
        """
        Загрузить файл метрик в облачное хранилище S3
        
        Args:
            file: File object из запроса Flask (werkzeug.FileStorage)
            
        Returns:
            Результат загрузки
        """
        if not self._s3:
            return {
                'success': False,
                'error': 'S3 клиент не инициализирован'
            }
        
        try:
            filename = file.filename
            
            # Считываем содержимое файла
            file_content = file.read()
            
            # Загружаем в S3
            self._s3.put_object(
                Bucket=self._bucket_name,
                Key=filename,
                Body=file_content,
                ContentType='application/json'
            )
            
            return {
                'success': True,
                'filename': filename,
                'size': len(file_content)
            }
            
        except Exception as e:
            print(f"Ошибка загрузки файла {file.filename}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_average_performance(self, hostname: str, from_date_str: str, to_date_str: str) -> Dict:
        """
        Получить средние показатели производительности за период.
        
        Args:
            hostname: Название компьютера
            from_date_str: Начальная дата в формате YYYY-MM-DD
            to_date_str: Конечная дата в формате YYYY-MM-DD
            
        Returns:
            Средние значения всех показателей в указанном формате
        """
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            return {
                'success': False,
                'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD',
                'average': {}
            }
        
        if from_date > to_date:
            return {
                'success': False,
                'error': 'Начальная дата не может быть больше конечной',
                'average': {}
            }
        
        sanitized_name = self._sanitize_hostname(hostname)
        all_metrics = []
        current_date = from_date
        
        while current_date <= to_date:
            file_key = f"{sanitized_name}_{current_date.isoformat()}.json"
            
            if self.file_exists(file_key):
                records = self.read_all_records(file_key)
                
                for record in records:
                    if record.get('type') == 'metric' and 'data' in record:
                        all_metrics.append(record['data'])
            
            current_date += timedelta(days=1)
        
        if not all_metrics:
            return {
                'success': True,
                'hostname': hostname,
                'from_date': from_date_str,
                'to_date': to_date_str,
                'metrics_count': 0,
                'average': {}
            }
        
        # Вычисляем средние значения
        def avg(key):
            values = [m.get(key) for m in all_metrics if m.get(key) is not None]
            return round(sum(values) / len(values), 2) if values else None
        
        # Получаем последние общие показатели (общий объем диска и ОЗУ не меняется)
        last_metric = all_metrics[-1]
        
        average = {
            'cpu_usage': avg('cpu_usage'),
            'ram_usage': avg('ram_usage'),
            'ram_used_gb': avg('ram_used_gb'),
            'ram_total_gb': last_metric.get('ram_total_gb'),
            'disk_usage': avg('disk_usage'),
            'disk_used_gb': avg('disk_used_gb'),
            'disk_total_gb': last_metric.get('disk_total_gb'),
            'network_sent_mb': avg('network_sent_mb'),
            'network_recv_mb': avg('network_recv_mb'),
            'uptime_seconds': last_metric.get('uptime_seconds')
        }
        
        return {
            'success': True,
            'hostname': hostname,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'metrics_count': len(all_metrics),
            'average': average
        }

    def get_all_performance(self, hostname: str, from_date_str: str, to_date_str: str) -> Dict:
        """
        Получить все показатели производительности за период без усреднения.
        
        Args:
            hostname: Название компьютера
            from_date_str: Начальная дата в формате YYYY-MM-DD
            to_date_str: Конечная дата в формате YYYY-MM-DD
            
        Returns:
            Список всех метрик производительности в хронологическом порядке
        """
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            return {
                'success': False,
                'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD',
                'performance': []
            }
        
        if from_date > to_date:
            return {
                'success': False,
                'error': 'Начальная дата не может быть больше конечной',
                'performance': []
            }
        
        sanitized_name = self._sanitize_hostname(hostname)
        all_performance = []
        current_date = from_date
        
        while current_date <= to_date:
            file_key = f"{sanitized_name}_{current_date.isoformat()}.json"
            
            if self.file_exists(file_key):
                records = self.read_all_records(file_key)
                
                for record in records:
                    if record.get('type') == 'metric' and 'data' in record:
                        all_performance.append({
                            'timestamp': record.get('timestamp'),
                            **record['data']
                        })
            
            current_date += timedelta(days=1)
        
        all_performance.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            'success': True,
            'hostname': hostname,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'count': len(all_performance),
            'performance': all_performance
        }

    def get_all_events(self, hostname: str, from_date_str: str, to_date_str: str) -> Dict:
        """
        Получить все события за период.
        
        Args:
            hostname: Название компьютера
            from_date_str: Начальная дата в формате YYYY-MM-DD
            to_date_str: Конечная дата в формате YYYY-MM-DD
            
        Returns:
            Список всех событий за период
        """
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            return {
                'success': False,
                'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD',
                'events': []
            }
        
        if from_date > to_date:
            return {
                'success': False,
                'error': 'Начальная дата не может быть больше конечной',
                'events': []
            }
        
        sanitized_name = self._sanitize_hostname(hostname)
        all_events = []
        current_date = from_date
        
        while current_date <= to_date:
            file_key = f"{sanitized_name}_{current_date.isoformat()}.json"
            
            if self.file_exists(file_key):
                records = self.read_all_records(file_key)
                
                for record in records:
                    if record.get('type') == 'user_action' or record.get('type') == 'windows_event':
                        all_events.append(record)
            
            current_date += timedelta(days=1)
        
        all_events.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            'success': True,
            'hostname': hostname,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'count': len(all_events),
            'events': all_events
        }

    def get_events_statistics(self, hostname: str, from_date_str: str, to_date_str: str) -> Dict:
        """
        Получить статистику по количеству каждого типа событий за период.
        
        Args:
            hostname: Название компьютера
            from_date_str: Начальная дата в формате YYYY-MM-DD
            to_date_str: Конечная дата в формате YYYY-MM-DD
            
        Returns:
            Статистика с общим количеством каждого типа события
        """
        events_data = self.get_all_events(hostname, from_date_str, to_date_str)
        
        if not events_data.get('success'):
            return events_data
        
        events = events_data.get('events', [])
        statistics = {}
        
        for event in events:
            action_type = event.get('data', {}).get('action_type', event.get('type', 'unknown'))
            if action_type not in statistics:
                statistics[action_type] = 0
            statistics[action_type] += 1
        
        return {
            'success': True,
            'hostname': hostname,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'total_events': len(events),
            'statistics': statistics
        }

    def get_anomalies(self, hostname: str, from_date_str: str, to_date_str: str,
                     cpu_threshold: float = 90.0, ram_threshold: float = 90.0) -> Dict:
        """
        Получить аномалии (высокая нагрузка CPU/RAM) за период.
        
        Args:
            hostname: Название компьютера
            from_date_str: Начальная дата в формате YYYY-MM-DD
            to_date_str: Конечная дата в формате YYYY-MM-DD
            cpu_threshold: Порог CPU в процентах
            ram_threshold: Порог RAM в процентах
            
        Returns:
            Список аномалий за период
        """
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            return {
                'success': False,
                'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD',
                'anomalies': []
            }
        
        if from_date > to_date:
            return {
                'success': False,
                'error': 'Начальная дата не может быть больше конечной',
                'anomalies': []
            }
        
        sanitized_name = self._sanitize_hostname(hostname)
        anomalies = []
        current_date = from_date
        
        while current_date <= to_date:
            file_key = f"{sanitized_name}_{current_date.isoformat()}.json"
            
            if self.file_exists(file_key):
                records = self.read_all_records(file_key)
                
                for record in records:
                    if record.get('type') == 'metric' and 'data' in record:
                        data = record['data']
                        cpu = data.get('cpu_usage')
                        ram = data.get('ram_usage')
                        
                        if (cpu is not None and cpu > cpu_threshold) or (ram is not None and ram > ram_threshold):
                            anomalies.append({
                                'timestamp': record.get('timestamp'),
                                'cpu_usage': cpu,
                                'ram_usage': ram,
                                'cpu_threshold': cpu_threshold,
                                'ram_threshold': ram_threshold
                            })
            
            current_date += timedelta(days=1)
        
        anomalies.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            'success': True,
            'hostname': hostname,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'cpu_threshold': cpu_threshold,
            'ram_threshold': ram_threshold,
            'count': len(anomalies),
            'anomalies': anomalies
        }
