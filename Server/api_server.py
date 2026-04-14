"""
API Server - Flask REST API для админки
Запускается отдельно от основного WebSocket сервера
"""
import sys
import os

# Добавляем путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from flask_cors import CORS

from config import API_CONFIG
from routes import (
    computers_bp,
    users_bp,
    statuses_bp,
    metrics_bp,
    dashboard_bp,
    auth_bp,
    sessions_bp  
)


def create_app():
    """Создание Flask приложения"""
    app = Flask(__name__)
    
    # CORS для доступа с админки
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Регистрация blueprints - ВСЕ ЭНДПОИНТЫ
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(computers_bp, url_prefix='/api/computers')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(statuses_bp, url_prefix='/api/statuses')
    app.register_blueprint(metrics_bp, url_prefix='/api/metrics')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(sessions_bp, url_prefix='/api/sessions') 

    # Health check
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'PC-RMDS API Server',
            'registered_blueprints': [
                '/api/auth',
                '/api/computers', 
                '/api/users',
                '/api/statuses',
                '/api/metrics',
                '/api/dashboard',
                '/api/sessions'  
            ]
        })
    
    # Корневой эндпоинт
    @app.route('/')
    def index():
        return jsonify({
            'service': 'PC-RMDS REST API',
            'version': '1.0.0',
            'endpoints': {
                'auth': '/api/auth',
                'computers': '/api/computers',
                'users': '/api/users',
                'statuses': '/api/statuses',
                'metrics': '/api/metrics',
                'dashboard': '/api/dashboard',
                'sessions': '/api/sessions',  
                'health': '/health'
            }
        })
    
    # Обработка ошибок
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'error': 'Endpoint not found'
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
    
    return app


def main():
    """Запуск сервера"""
    app = create_app()
    
    host = API_CONFIG['host']
    port = API_CONFIG['port']
    debug = API_CONFIG['debug']
    
    print(f"""
 ╔═══════════════════════════════════════════════════════════╗
 ║           PC-RMDS REST API Server                         ║
 ╠═══════════════════════════════════════════════════════════╣
 ║  Started at: http://{host}:{port}                         
 ║  Debug mode: {str(debug):5}                                  
 ╠═══════════════════════════════════════════════════════════╣
 ║  Endpoints:                                              ║
 ║    POST /api/auth/login          - Вход в систему        ║
 ║    POST /api/auth/register       - Регистрация           ║
 ║    POST /api/computers/register  - Регистрация компа     ║
 ║    GET  /api/computers           - Список компьютеров    ║
 ║    POST /api/sessions            - СОЗДАНИЕ СЕССИИ       ║
 ║    GET  /api/sessions            - Список сессий         ║
 ║    GET  /api/sessions/active     - Активные сессии       ║
 ║    PUT  /api/sessions/<id>       - Обновление сессии     ║
 ║    GET  /api/users               - Список пользователей  ║
 ║    GET  /api/statuses            - Список статусов       ║
 ║    GET  /api/metrics             - Метрики из S3         ║
 ║    GET  /api/dashboard/stats     - Статистика            ║
 ║    GET  /health                  - Health check          ║
 ╚═══════════════════════════════════════════════════════════╝
     """)
    
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True
    )


if __name__ == '__main__':
    main()