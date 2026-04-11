"""
Конфигурация API сервера
"""
import os

# MySQL Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '5.183.188.132'),
    'user': os.getenv('DB_USER', '2024_mysql_t_usr'),
    'password': os.getenv('DB_PASSWORD', 'uqnOzz3fbUqudcdM'),
    'db': os.getenv('DB_NAME', '2024_mysql_tim'),
    'charset': 'utf8mb4',
    'cursorclass': 'DictCursor'
}

# Cloud Storage Configuration (S3)
CLOUD_CONFIG = {
    'access_key': os.getenv('CLOUD_ACCESS_KEY', '1TUFGD6LDS8S8DGRFYMU'),
    'secret_key': os.getenv('CLOUD_SECRET_KEY', 'Vq3kZWM8HSxcxZNv4qLw9l63J80mj9fBsd80KumS'),
    'endpoint_url': os.getenv('CLOUD_ENDPOINT_URL', 'https://s3.regru.cloud'),
    'bucket_name': os.getenv('CLOUD_BUCKET_NAME', 'metrics-errors-logs')
}

# API Server Configuration
API_CONFIG = {
    'host': os.getenv('API_HOST', '0.0.0.0'),
    'port': int(os.getenv('API_PORT', 5000)),
    'debug': os.getenv('API_DEBUG', 'False').lower() == 'true',
    'api_key': os.getenv('API_KEY', ''),  # Optional API key for authentication
}

# Metrics Configuration
METRICS_CONFIG = {
    'max_points_per_request': 1000,  # Max data points per request
    'default_resolution': '30min',     # Default aggregation level
    'cache_ttl': 300,                  # Cache TTL in seconds
}

# Pagination
PAGINATION = {
    'default_limit': 20,
    'max_limit': 100,
}
