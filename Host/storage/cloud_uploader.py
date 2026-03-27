import json
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
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
                config=Config(signature_version='s3v4'),
                verify=True
            )
        except Exception as e:
            print(f"Ошибка инициализации S3: {e}")
            self.s3 = None
    
    def upload_file(self, file_path: Path) -> bool:
        if not self.s3 or not file_path.exists():
            return False
        
        try:
            object_name = file_path.name
            self.s3.upload_file(
                str(file_path), 
                self.bucket_name, 
                object_name,
                ExtraArgs={'ContentType': 'application/json'}
            )
            
            try:
                self.s3.head_object(Bucket=self.bucket_name, Key=object_name)
                return True
            except ClientError:
                return False
                    
        except Exception:
            return False
    
    def list_bucket_files(self):
        if not self.s3:
            return []
        
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket_name)
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents']]
            return []
        except Exception:
            return []
    
    def upload_end_of_day_files(self) -> int:
        uploaded = 0
        endofday_files = list(self.markers_folder.glob("endofday_*.json"))
        
        for marker_file in endofday_files:
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
                else:
                    if not file_path.exists() or sent_marker.exists():
                        marker_file.unlink()
            except Exception:
                pass
        
        return uploaded
    
    def upload_urgent_files(self) -> int:
        uploaded = 0
        urgent_files = list(self.markers_folder.glob("urgent_*.json"))
        
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
            except Exception:
                pass
        return uploaded
    
    def check_and_upload(self) -> int:
        uploaded = 0
        uploaded += self.upload_end_of_day_files()
        uploaded += self.upload_urgent_files()
        return uploaded