import json
import boto3
from botocore.config import Config
from pathlib import Path

from utils.constants import CLOUD_CONFIG


class CloudUploader:
    
    def __init__(self):
        self.access_key = CLOUD_CONFIG['access_key']
        self.secret_key = CLOUD_CONFIG['secret_key']
        self.endpoint_url = CLOUD_CONFIG['endpoint_url']
        self.bucket_name = CLOUD_CONFIG['bucket_name']
        
        self.s3 = None
        self.temps_folder = Path(__file__).parent.parent / "temps"
        self.markers_folder = self.temps_folder / ".markers"
        
        self.init_s3_client()
    
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
    
    def upload_file(self, file_path: Path) -> bool:
        if not self.s3 or not file_path.exists():
            return False
        
        try:
            object_name = file_path.name
            self.s3.upload_file(str(file_path), self.bucket_name, object_name)
            return True
        except Exception as e:
            print(f"Ошибка загрузки {object_name}: {e}")
            return False
    
    def upload_end_of_day_files(self) -> int:
        uploaded = 0
        for marker_file in self.markers_folder.glob("endofday_*.json"):
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
            except:
                pass
        return uploaded
    
    def upload_urgent_files(self) -> int:
        uploaded = 0
        for marker_file in self.markers_folder.glob("urgent_*.json"):
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
            except:
                pass
        return uploaded
    
    def check_and_upload(self) -> int:
        uploaded = 0
        uploaded += self.upload_end_of_day_files()
        uploaded += self.upload_urgent_files()
        return uploaded