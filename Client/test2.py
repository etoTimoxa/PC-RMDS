import boto3
from botocore.config import Config
from pathlib import Path
import os

# ==================== НАСТРОЙКИ ====================
ACCESS_KEY = "1TUFGD6LDS8S8DGRFYMU"
SECRET_KEY = "Vq3kZWM8HSxcxZNv4qLw9l63J80mj9fBsd80KumS"
ENDPOINT_URL = "https://s3.regru.cloud"
BUCKET_NAME = "metrics-errors-logs"

# Папка куда скачивать файлы
DOWNLOAD_FOLDER = r"C:\Users\Тимофей\Desktop\metric_out"

# ==================== ПОДКЛЮЧЕНИЕ ====================
s3 = boto3.client(
    's3',
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    config=Config(signature_version='s3v4')
)

# ==================== ПОЛУЧИТЬ СПИСОК ФАЙЛОВ ====================
print(f"📦 Подключаемся к бакету: {BUCKET_NAME}")
print("=" * 50)

try:
    # Получаем список всех файлов в бакете
    response = s3.list_objects_v2(Bucket=BUCKET_NAME)
    
    if 'Contents' not in response:
        print("❌ Бакет пуст! Нет файлов для скачивания.")
        exit()
    
    files = response['Contents']
    print(f"📄 Найдено файлов: {len(files)}")
    print("-" * 50)
    
    # Показываем список файлов
    for obj in files:
        file_name = obj['Key']
        file_size = obj['Size'] / 1024  # в KB
        print(f"   📄 {file_name} ({file_size:.1f} KB)")
    
    print("=" * 50)
    
    # ==================== СОЗДАЕМ ПАПКУ ДЛЯ СКАЧИВАНИЯ ====================
    Path(DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    print(f"📁 Папка для скачивания: {DOWNLOAD_FOLDER}")
    print("=" * 50)
    
    # ==================== СКАЧИВАЕМ ФАЙЛЫ ====================
    downloaded = 0
    failed = 0
    
    for obj in files:
        file_name = obj['Key']
        local_path = os.path.join(DOWNLOAD_FOLDER, file_name)
        file_size = obj['Size'] / 1024
        
        print(f"📥 Скачивание: {file_name} ({file_size:.1f} KB)")
        
        try:
            s3.download_file(BUCKET_NAME, file_name, local_path)
            print(f"   ✅ Сохранено: {local_path}")
            downloaded += 1
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"✅ Скачано: {downloaded}")
    print(f"❌ Ошибок: {failed}")
    print("Готово!")
    
except Exception as e:
    print(f"❌ Ошибка при получении списка файлов: {e}")