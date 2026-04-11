"""
Routes package - экспорт всех blueprint'ов
"""
from .computers import computers_bp
from .users import users_bp
from .sessions import sessions_bp
from .metrics import metrics_bp
from .dashboard import dashboard_bp

__all__ = [
    'computers_bp',
    'users_bp',
    'sessions_bp',
    'metrics_bp',
    'dashboard_bp'
]
