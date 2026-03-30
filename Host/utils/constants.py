import pymysql.cursors
import sys
from pathlib import Path


def get_base_path() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


STATUS_ACTIVE = 1
STATUS_DISCONNECTED = 2
STATUS_TIMEOUT = 3
STATUS_ERROR = 4
STATUS_PENDING = 5

DB_CONFIG = {
    'host': '5.183.188.132',
    'user': '2024_mysql_t_usr',
    'password': 'uqnOzz3fbUqudcdM',
    'db': '2024_mysql_tim',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

CLOUD_CONFIG = {
    'access_key': '1TUFGD6LDS8S8DGRFYMU',
    'secret_key': 'Vq3kZWM8HSxcxZNv4qLw9l63J80mj9fBsd80KumS',
    'endpoint_url': 'https://s3.regru.cloud',
    'bucket_name': 'metrics-errors-logs'
}

METRICS_INTERVAL = 1800
WINDOWS_EVENTS_INTERVAL = 1800
HEARTBEAT_INTERVAL = 300
ACTIVITY_UPDATE_INTERVAL = 900
URGENT_CHECK_INTERVAL = 60

ANOMALY_THRESHOLDS = {
    'cpu_usage': 90,
    'ram_usage': 90,
    'disk_usage': 100
}

CRITICAL_EVENT_IDS = [1001, 1003, 1005, 1010, 1011, 1015, 1074, 1076, 1078, 1098, 1099, 1101]

BASE_PATH = get_base_path()
TEMP_FOLDER = BASE_PATH / "temps"