import json
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
import sys
import re
import time
from datetime import datetime
from typing import Tuple, Optional

from utils.constants import CLOUD_CONFIG
from utils.platform_utils import get_data_dir, ensure_dirs


class CloudUploader:
    """Загрузчик файлов в облако с поддержкой повторных попыток и проверкой"""
    
    # Максимальное количество попыток загрузки
    MAX_RETRY_ATTEMPTS = 3
    # Задержка между попытками (в секундах)
    RETRY_DELAY = 5
    # Максимальное количество файлов в очереди повторной отправки
    MAX_RETRY_QUEUE_SIZE = 100
    
    def __init__(self, json_logger=None):
        self.access_key = CLOUD_CONFIG['access_key']
        self.secret_key = CLOUD_CONFIG['secret_key']
        self.endpoint_url = CLOUD_CONFIG['endpoint_url']
        self.bucket_name = CLOUD_CONFIG['bucket_name']
        
        self.s3 = None
        # Используем platform_utils для определения правильной директории
        ensure_dirs()
        self.temps_folder = get_data_dir() / "temps"
        self.markers_folder = self.temps_folder / ".markers"
        
        self.temps_folder.mkdir(parents=True, exist_ok=True)
        self.markers_folder.mkdir(parents=True, exist_ok=True)
        
        self.json_logger = json_logger  # Ссылка на JSONLogger для сброса флага
        self.init_s3_client()
        
        # Очередь файлов для повторной отправки
        self.retry_queue = []
        self._load_retry_queue()
    
    def set_json_logger(self, json_logger):
        """Устанавливает ссылку на JSONLogger для сброса флага после отправки"""
        self.json_logger = json_logger
    
    def init_s3_client(self):
        """Инициализация S3 клиента"""
        try:
            self.s3 = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(
                    signature_version='s3v4',
                    retries={'max_attempts': 3, 'mode': 'standard'}
                )
            )
        except Exception as e:
            print(f"Ошибка инициализации S3: {e}")
            self.s3 = None
    
    def _load_retry_queue(self):
        """Загрузка очереди повторной отправки из файла"""
        retry_file = self.markers_folder / "retry_queue.json"
        if retry_file.exists():
            try:
                with open(retry_file, 'r') as f:
                    self.retry_queue = json.load(f)
            except:
                self.retry_queue = []
    
    def _save_retry_queue(self):
        """Сохранение очереди повторной отправки"""
        retry_file = self.markers_folder / "retry_queue.json"
        try:
            with open(retry_file, 'w') as f:
                json.dump(self.retry_queue, f)
        except:
            pass
    
    def _add_to_retry_queue(self, file_name: str, attempt: int = 0):
        """Добавление файла в очередь повторной отправки"""
        if len(self.retry_queue) >= self.MAX_RETRY_QUEUE_SIZE:
            # Удаляем самые старые записи если очередь переполнена
            self.retry_queue = self.retry_queue[-50:]
        
        self.retry_queue.append({
            'file_name': file_name,
            'attempt': attempt + 1,
            'last_attempt': datetime.now().isoformat()
        })
        self._save_retry_queue()
    
    def file_exists_in_cloud(self, file_name: str) -> bool:
        """Проверяет, существует ли файл в облаке"""
        if not self.s3:
            return False
        
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=file_name)
            return True
        except ClientError as e:
            # Файл не найден
            if e.response['Error']['Code'] == '404':
                return False
            # Другая ошибка
            print(f"Ошибка проверки файла в облаке: {e}")
            return False
        except Exception as e:
            print(f"Ошибка проверки файла в облаке: {e}")
            return False
    
    def upload_file(self, file_path: Path, max_retries: int = None) -> Tuple[bool, str]:
        """
        Загружает файл в облако с поддержкой повторных попыток.
        
        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке или "OK")
        """
        if max_retries is None:
            max_retries = self.MAX_RETRY_ATTEMPTS
            
        if not self.s3 or not file_path.exists():
            return False, "S3 клиент не инициализирован или файл не существует"
        
        object_name = file_path.name
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                # Проверяем, существует ли файл в облаке
                if self.file_exists_in_cloud(object_name):
                    return True, "OK"
                
                # Загружаем файл
                self.s3.upload_file(
                    str(file_path), 
                    self.bucket_name, 
                    object_name,
                    ExtraArgs={
                        'ContentType': 'application/json',
                        'ACL': 'private'
                    }
                )
                
                # Проверяем, что файл действительно загрузился
                if self.file_exists_in_cloud(object_name):
                    return True, "OK"
                else:
                    last_error = "Файл не найден после загрузки"
                    
            except NoCredentialsError as e:
                last_error = f"Ошибка аутентификации: {str(e)}"
                # Не пытаемся повторить при ошибке аутентификации
                break
            except ClientError as e:
                last_error = f"Ошибка S3: {str(e)}"
                # Некоторые ошибки не стоит повторять
                error_code = e.response['Error'].get('Code', '')
                if error_code in ['AccessDenied', 'NoSuchBucket', 'InvalidAccessKeyId']:
                    break
            except Exception as e:
                last_error = f"Ошибка загрузки: {str(e)}"
            
            # Если это не последняя попытка, ждем перед повтором
            if attempt < max_retries:
                print(f"Попытка {attempt}/{max_retries} не удалась. Повтор через {self.RETRY_DELAY} сек...")
                time.sleep(self.RETRY_DELAY)
        
        return False, last_error
    
    def upload_end_of_day_files(self) -> int:
        """Загружает файлы за прошедшие дни в хронологическом порядке"""
        uploaded = 0
        endofday_files = list(self.markers_folder.glob("endofday_*.json"))
        
        # Сортируем файлы по дате в имени
        def extract_date(filename):
            match = re.search(r'(\d{4}-\d{2}-\d{2})\.json$', filename.name)
            if match:
                return match.group(1)
            return ''
        
        endofday_files.sort(key=extract_date)
        
        for marker_file in endofday_files:
            try:
                with open(marker_file, 'r') as f:
                    file_name = f.read().strip()
                
                file_path = self.temps_folder / file_name
                sent_marker = self.markers_folder / f"sent_{file_name}"
                
                # Если файл уже отправлен, удаляем маркер и пропускаем
                if sent_marker.exists():
                    marker_file.unlink()
                    continue
                
                # Проверяем, существует ли файл в облаке
                if self.file_exists_in_cloud(file_name):
                    # Отмечаем как отправленный
                    sent_marker.touch()
                    marker_file.unlink()
                    continue
                
                if file_path.exists():
                    success, message = self.upload_file(file_path)
                    
                    if success:
                        sent_marker.touch()
                        uploaded += 1
                        # Сбрасываем флаг срочной отправки если это urgent файл
                        if self.json_logger:
                            self.json_logger.reset_urgent_flag()
                    else:
                        print(f"Не удалось загрузить файл {file_name}: {message}")
                        # Добавляем в очередь повторной отправки
                        self._add_to_retry_queue(file_name)
                
                # Удаляем маркер в любом случае, чтобы не пытаться снова сразу
                marker_file.unlink()
                
            except Exception as e:
                print(f"Ошибка при загрузке файла: {e}")
                try:
                    marker_file.unlink()
                except:
                    pass
        
        return uploaded
    
    def upload_urgent_files(self) -> int:
        """Загружает срочные файлы (при аномалиях)"""
        uploaded = 0
        urgent_files = list(self.markers_folder.glob("urgent_*.json"))
        
        for marker_file in urgent_files:
            try:
                with open(marker_file, 'r') as f:
                    file_name = f.read().strip()
                
                file_path = self.temps_folder / file_name
                sent_marker = self.markers_folder / f"sent_{file_name}"
                
                # Если файл уже отправлен, удаляем маркер
                if sent_marker.exists():
                    marker_file.unlink()
                    continue
                
                # Проверяем, существует ли файл в облаке
                if self.file_exists_in_cloud(file_name):
                    sent_marker.touch()
                    marker_file.unlink()
                    continue
                
                if file_path.exists():
                    success, message = self.upload_file(file_path, max_retries=5)
                    
                    if success:
                        sent_marker.touch()
                        uploaded += 1
                        # Сбрасываем флаг срочной отправки
                        if self.json_logger:
                            self.json_logger.reset_urgent_flag()
                    else:
                        print(f"Не удалось загрузить срочный файл {file_name}: {message}")
                        # Добавляем в очередь повторной отправки с высоким приоритетом
                        self._add_to_retry_queue(file_name)
                
                # Удаляем маркер после попытки отправки
                marker_file.unlink()
                
            except Exception as e:
                print(f"Ошибка при срочной загрузке: {e}")
                try:
                    marker_file.unlink()
                except:
                    pass
        
        return uploaded
    
    def process_retry_queue(self) -> int:
        """Обработка очереди повторной отправки"""
        uploaded = 0
        remaining_queue = []
        
        for item in self.retry_queue:
            file_name = item['file_name']
            attempt = item.get('attempt', 0)
            
            # Проверяем, не превышено ли максимальное количество попыток
            if attempt >= self.MAX_RETRY_ATTEMPTS:
                print(f"Превышено максимальное количество попыток для {file_name}")
                continue
            
            file_path = self.temps_folder / file_name
            sent_marker = self.markers_folder / f"sent_{file_name}"
            
            # Если файл уже отправлен, пропускаем
            if sent_marker.exists():
                continue
            
            # Проверяем, существует ли файл в облаке
            if self.file_exists_in_cloud(file_name):
                sent_marker.touch()
                continue
            
            # Проверяем, существует ли локальный файл
            if not file_path.exists():
                print(f"Файл {file_name} не найден локально, пропускаем")
                continue
            
            # Пытаемся загрузить
            success, message = self.upload_file(file_path)
            
            if success:
                sent_marker.touch()
                uploaded += 1
            else:
                print(f"Повторная загрузка {file_name} не удалась: {message}")
                # Возвращаем в очередь
                remaining_queue.append(item)
        
        self.retry_queue = remaining_queue
        self._save_retry_queue()
        
        return uploaded
    
    def check_and_upload(self) -> int:
        """Проверяет и загружает все ожидающие файлы"""
        uploaded = 0
        
        # Сначала загружаем срочные файлы
        urgent_uploaded = self.upload_urgent_files()
        if urgent_uploaded > 0:
            uploaded += urgent_uploaded
        
        # Затем загружаем файлы за прошедшие дни
        endofday_uploaded = self.upload_end_of_day_files()
        if endofday_uploaded > 0:
            uploaded += endofday_uploaded
        
        # Обрабатываем очередь повторной отправки
        retry_uploaded = self.process_retry_queue()
        if retry_uploaded > 0:
            uploaded += retry_uploaded
        
        return uploaded
    
    def verify_and_cleanup(self) -> int:
        """
        Проверяет отправленные файлы в облаке и удаляет локальные копии,
        если они успешно загружены.
        
        Returns:
            int: Количество удаленных файлов
        """
        cleaned = 0
        sent_markers = list(self.markers_folder.glob("sent_*.json"))
        
        for marker in sent_markers:
            file_name = marker.name.replace("sent_", "")
            file_path = self.temps_folder / file_name
            
            if not file_path.exists():
                # Файл уже удален, удаляем маркер
                try:
                    marker.unlink()
                except:
                    pass
                continue
            
            # Проверяем, существует ли файл в облаке
            if self.file_exists_in_cloud(file_name):
                # Файл в облаке, можно удалять локальную копию
                try:
                    file_path.unlink()
                    marker.unlink()
                    cleaned += 1
                    print(f"Удален локальный файл {file_name} (подтверждено в облаке)")
                except Exception as e:
                    print(f"Не удалось удалить файл {file_name}: {e}")
            else:
                # Файл не в облаке, проверяем возраст
                try:
                    file_mtime = file_path.stat().st_mtime
                    file_age_days = (time.time() - file_mtime) / (60 * 60 * 24)
                    
                    # Если файлу больше 7 дней и его нет в облаке - удаляем
                    if file_age_days > 7:
                        file_path.unlink()
                        marker.unlink()
                        cleaned += 1
                        print(f"Удален старый файл {file_name} (возраст {file_age_days:.1f} дней)")
                except Exception as e:
                    print(f"Ошибка проверки файла {file_name}: {e}")
        
        return cleaned
    
    def get_upload_stats(self) -> dict:
        """Получение статистики загрузок"""
        stats = {
            'pending_files': 0,
            'sent_files': 0,
            'urgent_files': 0,
            'retry_queue_size': len(self.retry_queue),
            'total_local_size_mb': 0
        }
        
        # Подсчет отправленных файлов
        sent_markers = list(self.markers_folder.glob("sent_*.json"))
        stats['sent_files'] = len(sent_markers)
        
        # Подсчет ожидающих файлов
        for file_path in self.temps_folder.glob("*.json"):
            if file_path.name.startswith('.'):
                continue
            
            file_name = file_path.name
            sent_marker = self.markers_folder / f"sent_{file_name}"
            
            if not sent_marker.exists():
                stats['pending_files'] += 1
                try:
                    stats['total_local_size_mb'] += file_path.stat().st_size / (1024 * 1024)
                except:
                    pass
            
            # Проверка на срочные файлы
            urgent_marker = self.markers_folder / f"urgent_{file_name}"
            if urgent_marker.exists():
                stats['urgent_files'] += 1
        
        return stats