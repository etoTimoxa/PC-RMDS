"""
Notifications routes - эндпоинты для уведомлений о критических событиях и аномалиях
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from services.mysql_service import MySQLService
from services.cloud_service import CloudService

notifications_bp = Blueprint('notifications', __name__)
mysql = MySQLService()
cloud = CloudService()

CRITICAL_EVENT_TYPES = {
    'shutdown': 'Выключение системы',
    'restart': 'Перезагрузка системы',
    'windows_restart': 'Перезагрузка Windows',
    'windows_event': 'Критическое событие Windows',
    'sleep': 'Спящий режим',
    'system_boot': 'Загрузка системы',
}


@notifications_bp.route('/recent', methods=['GET'])
def get_recent_notifications():
    """
    GET /api/notifications/recent
    Получить последние уведомления о критических событиях и аномалиях
    по всем компьютерам.

    Query params:
        - hours: int (по умолчанию 2) - за сколько часов проверять
        - cpu_threshold: float (по умолчанию 90.0)
        - ram_threshold: float (по умолчанию 90.0)
        - limit: int (по умолчанию 50)
    """
    try:
        hours = request.args.get('hours', 2, type=int)
        cpu_threshold = request.args.get('cpu_threshold', 90.0, type=float)
        ram_threshold = request.args.get('ram_threshold', 90.0, type=float)
        limit = request.args.get('limit', 50, type=int)
        
        now = datetime.now()
        from_time = now - timedelta(hours=hours)
        from_str = from_time.strftime('%Y-%m-%d')
        to_str = now.strftime('%Y-%m-%d')
        from_iso = from_time.isoformat()
        to_iso = now.isoformat()
        
        # Получаем все компьютеры
        computers = mysql.fetch_all("""
            SELECT 
                c.computer_id, c.hostname, c.is_online, c.last_online,
                u.login, u.full_name
            FROM computer c
            LEFT JOIN user u ON c.user_id = u.user_id
            ORDER BY c.hostname
        """)
        
        notifications = []
        
        for comp in computers:
            computer_id = comp['computer_id']
            hostname = comp['hostname']
            
            if not hostname:
                continue
            
            # 1. Получаем критические события за период
            try:
                events_data = cloud.get_all_events(hostname, from_str, to_str)
                if events_data and events_data.get('success', True):
                    events = events_data.get('events', [])
                    for event in events:
                        event_type = event.get('type', '')
                        data = event.get('data', {})
                        timestamp = event.get('timestamp', '')
                        
                        if event_type in CRITICAL_EVENT_TYPES:
                            # Фильтруем по времени (последние N часов)
                            try:
                                ev_time = datetime.fromisoformat(timestamp)
                                if ev_time < from_time:
                                    continue
                            except (ValueError, TypeError):
                                pass
                            
                            notifications.append({
                                'computer_id': computer_id,
                                'hostname': hostname,
                                'user_login': comp.get('login', ''),
                                'is_online': comp.get('is_online', 0),
                                'type': 'critical_event',
                                'event_type': event_type,
                                'event_label': CRITICAL_EVENT_TYPES.get(event_type, event_type),
                                'timestamp': timestamp,
                                'description': _get_event_description(event),
                                'severity': 'high' if event_type in ('shutdown', 'restart', 'windows_restart') else 'medium'
                            })
            except Exception as e:
                print(f"[NOTIFICATIONS] Ошибка получения событий для {hostname}: {e}")
            
            # 2. Получаем аномалии за период
            try:
                anomalies_data = cloud.get_anomalies(hostname, from_str, to_str, cpu_threshold, ram_threshold)
                if anomalies_data and anomalies_data.get('success', True):
                    anomalies = anomalies_data.get('anomalies', [])
                    for anomaly in anomalies:
                        timestamp = anomaly.get('timestamp', '')
                        try:
                            an_time = datetime.fromisoformat(timestamp)
                            if an_time < from_time:
                                continue
                        except (ValueError, TypeError):
                            pass
                        
                        cpu_val = anomaly.get('cpu_usage', 0)
                        ram_val = anomaly.get('ram_usage', 0)
                        
                        notifications.append({
                            'computer_id': computer_id,
                            'hostname': hostname,
                            'user_login': comp.get('login', ''),
                            'is_online': comp.get('is_online', 0),
                            'type': 'anomaly_spike',
                            'event_type': 'anomaly',
                            'event_label': f"Скачок CPU {cpu_val}% / RAM {ram_val}%",
                            'timestamp': timestamp,
                            'cpu_usage': cpu_val,
                            'ram_usage': ram_val,
                            'description': f"CPU: {cpu_val}% | RAM: {ram_val}%",
                            'severity': 'critical' if (cpu_val >= 95 or ram_val >= 95) else 'high'
                        })
            except Exception as e:
                print(f"[NOTIFICATIONS] Ошибка получения аномалий для {hostname}: {e}")
        
        # Сортируем по времени (сначала новые)
        notifications.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Ограничиваем количество
        notifications = notifications[:limit]
        
        # Считаем статистику
        total = len(notifications)
        critical_count = sum(1 for n in notifications if n.get('severity') == 'critical')
        high_count = sum(1 for n in notifications if n.get('severity') == 'high')
        event_count = sum(1 for n in notifications if n.get('type') == 'critical_event')
        anomaly_count = sum(1 for n in notifications if n.get('type') == 'anomaly_spike')
        
        return jsonify({
            'success': True,
            'data': {
                'notifications': notifications,
                'total': total,
                'critical_count': critical_count,
                'high_count': high_count,
                'event_count': event_count,
                'anomaly_count': anomaly_count,
                'period_hours': hours,
                'from': from_iso,
                'to': to_iso
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _get_event_description(event):
    """Формирует описание события"""
    event_type = event.get('type', '')
    data = event.get('data', {})
    
    descriptions = {
        'user_action': data.get('description', 'Действие пользователя'),
        'windows_event': data.get('message', 'Событие Windows'),
        'system_boot': 'Загрузка системы',
        'shutdown': 'Выключение системы',
        'restart': 'Перезагрузка системы',
        'windows_restart': 'Перезагрузка Windows',
        'sleep': 'Переход в спящий режим',
    }
    
    return descriptions.get(event_type, str(event_type))