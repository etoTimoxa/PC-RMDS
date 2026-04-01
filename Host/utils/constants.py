import pymysql.cursors
import sys
from pathlib import Path


def get_base_path() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


# Статусы сессий
STATUS_ACTIVE = 1
STATUS_DISCONNECTED = 2
STATUS_TIMEOUT = 3
STATUS_ERROR = 4
STATUS_PENDING = 5

# Роли пользователей
ROLE_CLIENT = 1
ROLE_ADMIN = 2
ROLE_SUPERADMIN = 3

# Типы компьютеров
COMPUTER_TYPE_CLIENT = 'client'
COMPUTER_TYPE_ADMIN = 'admin'

# Конфигурация базы данных
DB_CONFIG = {
    'host': '5.183.188.132',
    'user': '2024_mysql_t_usr',
    'password': 'uqnOzz3fbUqudcdM',
    'db': '2024_mysql_tim',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# Конфигурация облачного хранилища
CLOUD_CONFIG = {
    'access_key': '1TUFGD6LDS8S8DGRFYMU',
    'secret_key': 'Vq3kZWM8HSxcxZNv4qLw9l63J80mj9fBsd80KumS',
    'endpoint_url': 'https://s3.regru.cloud',
    'bucket_name': 'metrics-errors-logs'
}

# Интервалы сбора данных (в секундах)
METRICS_INTERVAL = 1800  # 30 минут
WINDOWS_EVENTS_INTERVAL = 1800  # 30 минут
HEARTBEAT_INTERVAL = 300  # 5 минут
ACTIVITY_UPDATE_INTERVAL = 900  # 15 минут
URGENT_CHECK_INTERVAL = 60  # 1 минута

# Пороги аномалий
ANOMALY_THRESHOLDS = {
    'cpu_usage': 90,
    'ram_usage': 90,
    'disk_usage': 100
}

# Критические ID событий Windows
CRITICAL_EVENT_IDS = [1001, 1003, 1005, 1010, 1011, 1015, 1074, 1076, 1078, 1098, 1099, 1101]

# Типы действий пользователя (для логгирования)
USER_ACTION_TYPES = {
    'restart': 'Перезагрузка компьютера',
    'shutdown': 'Выключение компьютера',
    'registry_change': 'Изменение реестра',
    'update_install': 'Установка обновления',
    'config_change': 'Изменение конфигурации',
    'service_start': 'Запуск службы',
    'service_stop': 'Остановка службы',
    'software_install': 'Установка ПО',
    'software_uninstall': 'Удаление ПО',
    'file_download': 'Скачивание файла',
    'settings_change': 'Изменение настроек'
}

# Настройки безопасности
SECURITY_CONFIG = {
    'max_retry_attempts': 3,
    'retry_delay_seconds': 5,
    'file_verification_timeout': 30,
    'max_local_storage_days': 7
}

BASE_PATH = get_base_path()
TEMP_FOLDER = BASE_PATH / "temps"
