import os
import pymysql.cursors

STATUS_ACTIVE = 1
STATUS_DISCONNECTED = 2

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '5.183.188.132'),
    'user': os.getenv('DB_USER', '2024_mysql_t_usr'),
    'password': os.getenv('DB_PASSWORD', 'uqnOzz3fbUqudcdM'),
    'db': os.getenv('DB_NAME', '2024_mysql_tim'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

CLOUD_CONFIG = {
    'access_key': os.getenv('CLOUD_ACCESS_KEY', '1TUFGD6LDS8S8DGRFYMU'),
    'secret_key': os.getenv('CLOUD_SECRET_KEY', 'Vq3kZWM8HSxcxZNv4qLw9l63J80mj9fBsd80KumS'),
    'endpoint_url': os.getenv('CLOUD_ENDPOINT_URL', 'https://s3.regru.cloud'),
    'bucket_name': os.getenv('CLOUD_BUCKET_NAME', 'metrics-errors-logs')
}

METRICS_INTERVAL = 1800
WINDOWS_EVENTS_INTERVAL = 1800
ACTIVITY_UPDATE_INTERVAL = 900

ANOMALY_THRESHOLDS = {
    'cpu_usage': 90,
    'ram_usage': 90,
    'disk_usage': 100
}

CRITICAL_EVENT_IDS = [1001, 1003, 1005, 1010, 1011, 1015, 1074, 1076, 1078, 1098, 1099, 1101]

USER_ACTION_TYPES = {
    'windows_restart': {
        'description': 'Перезагрузка Windows',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'windows_shutdown': {
        'description': 'Выключение Windows',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'system_restart': {
        'description': 'Перезагрузка системы',
        'user_type': 'system',
        'is_remote_capable': False
    },
    'system_shutdown': {
        'description': 'Выключение системы',
        'user_type': 'system',
        'is_remote_capable': False
    },
    'remote_restart': {
        'description': 'Удалённая перезагрузка',
        'user_type': 'admin',
        'is_remote_capable': True
    },
    'remote_shutdown': {
        'description': 'Удалённое выключение',
        'user_type': 'admin',
        'is_remote_capable': True
    },
    'restart': {
        'description': 'Перезагрузка компьютера',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'shutdown': {
        'description': 'Выключение компьютера',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'registry_change': {
        'description': 'Изменение реестра',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'update_install': {
        'description': 'Установка обновления',
        'user_type': 'system',
        'is_remote_capable': False
    },
    'config_change': {
        'description': 'Изменение конфигурации',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'service_start': {
        'description': 'Запуск службы',
        'user_type': 'system',
        'is_remote_capable': False
    },
    'service_stop': {
        'description': 'Остановка службы',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'software_install': {
        'description': 'Установка ПО',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'software_uninstall': {
        'description': 'Удаление ПО',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'file_download': {
        'description': 'Скачивание файла',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'settings_change': {
        'description': 'Изменение настроек',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'sleep': {
        'description': 'Переход в спящий режим',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'hibernate': {
        'description': 'Гибернация',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'wake': {
        'description': 'Выход из сна',
        'user_type': 'any',
        'is_remote_capable': True
    },
    'system_boot': {
        'description': 'Загрузка системы',
        'user_type': 'system',
        'is_remote_capable': False
    }
}

