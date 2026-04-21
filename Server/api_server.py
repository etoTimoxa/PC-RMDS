"""
API Server - Flask REST API для админки
Запускается отдельно от основного WebSocket сервера
"""
import sys
import os
import atexit

# Добавляем путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

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

# Глобальная переменная для планировщика
scheduler = None


def close_inactive_sessions_job(app):
    """Задача для закрытия неактивных сессий"""
    with app.app_context():
        try:
            from routes.sessions import sessions_bp
            # Создаем тестовый запрос к эндпоинту
            with app.test_request_context():
                response = sessions_bp.dispatch_request('auto_close_inactive_sessions')
                if response and hasattr(response, 'json'):
                    data = response.json
                    print(f"[SCHEDULER] {data.get('message', 'OK')} - {data.get('data', {}).get('timestamp', '')}")
        except Exception as e:
            print(f"[SCHEDULER] Ошибка: {e}")


def create_app():
    """Создание Flask приложения"""
    global scheduler
    
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
    
    # Эндпоинт для ручного вызова закрытия сессий
    @app.route('/api/maintenance/close-inactive-sessions', methods=['POST'])
    def manual_close_inactive():
        """Ручной вызов закрытия неактивных сессий"""
        from routes.sessions import sessions_bp
        with app.test_request_context():
            response = sessions_bp.dispatch_request('auto_close_inactive_sessions')
            return response
    
    # Эндпоинт для проверки статуса планировщика
    @app.route('/api/maintenance/scheduler-status', methods=['GET'])
    def scheduler_status():
        """Проверка статуса планировщика"""
        if scheduler is None:
            return jsonify({
                'success': False,
                'error': 'Scheduler not initialized'
            }), 500
        
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': str(job.next_run_time) if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return jsonify({
            'success': True,
            'data': {
                'running': scheduler.running,
                'jobs': jobs
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
    
    # Настройка планировщика для авто-закрытия сессий
    scheduler = BackgroundScheduler()
    
    # Добавляем задачу - запуск каждую минуту
    scheduler.add_job(
        func=lambda: close_inactive_sessions_job(app),
        trigger='interval',
        minutes=1,
        id='close_inactive_sessions',
        replace_existing=True
    )
    
    scheduler.start()
    print("[SCHEDULER] Запущен планировщик авто-закрытия сессий (каждую минуту)")
    
    # Останавливаем планировщик при завершении приложения
    atexit.register(lambda: scheduler.shutdown() if scheduler else None)
    
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
 ║    POST /api/sessions/auto-close-inactive - Авто-закрытие ║
 ║    GET  /api/users               - Список пользователей  ║
 ║    GET  /api/statuses            - Список статусов       ║
 ║    GET  /api/metrics             - Метрики из S3         ║
 ║    GET  /api/dashboard/stats     - Статистика            ║
 ║    GET  /health                  - Health check          ║
 ╠═══════════════════════════════════════════════════════════╣
 ║  [SCHEDULER] Авто-закрытие неактивных сессий: КАЖДУЮ МИНУТУ ║
 ╚═══════════════════════════════════════════════════════════╝
     """)
    
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True,
        use_reloader=False  # Отключаем перезагрузчик, чтобы планировщик не запускался дважды
    )


if __name__ == '__main__':
    main()