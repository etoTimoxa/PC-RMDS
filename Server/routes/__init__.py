"""
Routes package - экспорт всех blueprint'ов
"""
from .computers import computers_bp
from .users import users_bp
from .statuses import statuses_bp
from .metrics import metrics_bp
from .dashboard import dashboard_bp
from .auth import auth_bp
from .sessions import sessions_bp

__all__ = [
    'computers_bp',
    'users_bp',
    'statuses_bp',
    'metrics_bp',
    'dashboard_bp',
    'sessions_bp',
    'auth_bp'
]