import json
import boto3
from botocore.config import Config
from pathlib import Path
import sys
import re
from datetime import datetime

from utils.constants import CLOUD_CONFIG
from utils.platform_utils import get_data_dir, ensure_dirs


class CloudUploader:
    
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
    
    def set_json_logger(self, json_logger):
        """Устанавливает ссылку на JSONLogger для сброса флага после отправки"""
        self.json_logger = json_logger
    
    def init_s3_client(self):
        try:
            self.s3 = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version='s3v4')
            )
        except Exception as e:
            print(f"Ошибка инициализации S3: {e}")
            self.s3 = None
    
    def file_exists_in_cloud(self, file_name: str) -> bool:
        """Проверяет, существует ли файл в облаке"""
        if not self.s3:
            return False
        
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=file_name)
            return True
        except:
            return False
    
    def upload_file(self, file_path: Path) -> bool:
        if not self.s3 or not file_path.exists():
            return False
        
        try:
            object_name = file_path.name
            # Проверяем, существует ли файл в облаке
            if self.file_exists_in_cloud(object_name):
                return False
            
            self.s3.upload_file(str(file_path), self.bucket_name, object_name)
            return True
        except Exception:
            return False
    
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
                    if self.upload_file(file_path):
                        sent_marker.touch()
                        uploaded += 1
                        # Сбрасываем флаг срочной отправки если это urgent файл
                        if self.json_logger:
                            self.json_logger.reset_urgent_flag()
                
                # Удаляем маркер в любом случае, чтобы не пытаться снова
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
                    if self.upload_file(file_path):
                        sent_marker.touch()
                        uploaded += 1
                        # Сбрасываем флаг срочной отправки
                        if self.json_logger:
                            self.json_logger.reset_urgent_flag()
                
                # Удаляем маркер после попытки отправки
                marker_file.unlink()
                
            except Exception as e:
                print(f"Ошибка при срочной загрузке: {e}")
                try:
                    marker_file.unlink()
                except:
                    pass
        
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
        
        return uploaded