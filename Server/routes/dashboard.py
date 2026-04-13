"""
Dashboard routes - эндпоинты для дашборда и агрегированной статистики
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

from services.mysql_service import MySQLService

dashboard_bp = Blueprint('dashboard', __name__)
mysql = MySQLService()


@dashboard_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    GET /api/dashboard/stats
    Получить общую статистику для дашборда.
    """
    try:
        stats = mysql.get_dashboard_stats()
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/computers-summary', methods=['GET'])
def get_computers_summary():
    """
    GET /api/dashboard/computers-summary
    Получить статистику по компьютерам (по типам, ОС, статусам).
    """
    try:
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                # По типам (client/admin)
                cursor.execute("""
                    SELECT 
                        computer_type,
                        COUNT(*) as count,
                        SUM(is_online) as online,
                        SUM(1 - is_online) as offline
                    FROM computer
                    GROUP BY computer_type
                """)
                by_type = cursor.fetchall()
                
                # По ОС
                cursor.execute("""
                    SELECT 
                        os.os_name,
                        os.os_version,
                        COUNT(*) as count,
                        SUM(c.is_online) as online
                    FROM computer c
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    GROUP BY os.os_name, os.os_version
                    ORDER BY count DESC
                """)
                by_os = cursor.fetchall()
                
                # Последняя активность (компьютеры онлайн)
                cursor.execute("""
                    SELECT 
                        c.computer_id,
                        c.hostname,
                        c.last_online,
                        c.is_online,
                        u.login,
                        u.full_name
                    FROM computer c
                    LEFT JOIN user u ON c.user_id = u.user_id
                    WHERE c.is_online = 1
                    ORDER BY c.last_online DESC
                    LIMIT 20
                """)
                online_computers = cursor.fetchall()
                
                # Компьютеры офлайн более 24 часов
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM computer
                    WHERE is_online = 0 
                    AND last_online < DATE_SUB(NOW(), INTERVAL 24 HOUR)
                """)
                offline_24h = cursor.fetchone()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'by_type': by_type,
                        'by_operating_system': by_os,
                        'online_computers': online_computers,
                        'offline_more_than_24h': offline_24h['count'] if offline_24h else 0
                    }
                })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/activity', methods=['GET'])
def get_activity():
    """
    GET /api/dashboard/activity
    Получить активность за период.
    
    Query params:
        - from: datetime (ISO format)
        - to: datetime (ISO format)
        - group_by: hour|day (по умолчанию hour)
    """
    try:
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        group_by = request.args.get('group_by', 'hour')
        
        if from_str:
            try:
                from_date = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            except ValueError:
                from_date = datetime.now() - timedelta(days=1)
        else:
            from_date = datetime.now() - timedelta(days=1)
        
        if to_str:
            try:
                to_date = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            except ValueError:
                to_date = datetime.now()
        else:
            to_date = datetime.now()
        
        timeline = mysql.get_activity_timeline(
            from_date=from_date,
            to_date=to_date,
            group_by=group_by
        )
        
        return jsonify({
            'success': True,
            'data': {
                'from': from_date.isoformat(),
                'to': to_date.isoformat(),
                'group_by': group_by,
                'timeline': timeline
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/top-users', methods=['GET'])
def get_top_users():
    """
    GET /api/dashboard/top-users
    Получить топ пользователей по активности.
    
    Query params:
        - limit: int (по умолчанию 10)
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        
        users = mysql.get_top_users(limit=limit)
        
        return jsonify({
            'success': True,
            'data': {
                'users': users,
                'total': len(users)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/sessions-summary', methods=['GET'])
def get_sessions_summary():
    """
    GET /api/dashboard/sessions-summary
    Получить сводку по сессиям.
    """
    try:
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                # Общая статистика сессий
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_sessions,
                        SUM(CASE WHEN status_id = 1 THEN 1 ELSE 0 END) as active,
                        SUM(CASE WHEN status_id = 2 THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status_id = 3 THEN 1 ELSE 0 END) as failed,
                        AVG(TIMESTAMPDIFF(SECOND, start_time, COALESCE(end_time, NOW()))) as avg_duration_seconds
                    FROM session
                """)
                general_stats = cursor.fetchone()
                
                # Сессии за последние 24 часа
                cursor.execute("""
                    SELECT COUNT(*) as count FROM session
                    WHERE start_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                """)
                sessions_24h = cursor.fetchone()
                
                # Сессии за последние 7 дней
                cursor.execute("""
                    SELECT COUNT(*) as count FROM session
                    WHERE start_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """)
                sessions_7d = cursor.fetchone()
                
                # Топ компьютеров по количеству сессий
                cursor.execute("""
                    SELECT 
                        c.computer_id,
                        c.hostname,
                        COUNT(s.session_id) as session_count,
                        MAX(s.start_time) as last_session
                    FROM computer c
                    LEFT JOIN session s ON s.computer_id = c.computer_id
                    GROUP BY c.computer_id, c.hostname
                    ORDER BY session_count DESC
                    LIMIT 10
                """)
                top_computers = cursor.fetchall()
                
                # Распределение по часам (для тепловой карты)
                cursor.execute("""
                    SELECT 
                        HOUR(start_time) as hour,
                        COUNT(*) as count
                    FROM session
                    WHERE start_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                    GROUP BY HOUR(start_time)
                    ORDER BY hour
                """)
                hourly_distribution = cursor.fetchall()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'total_sessions': general_stats['total_sessions'] or 0,
                        'active_sessions': general_stats['active'] or 0,
                        'completed_sessions': general_stats['completed'] or 0,
                        'failed_sessions': general_stats['failed'] or 0,
                        'avg_duration_seconds': round(general_stats['avg_duration_seconds'] or 0, 0),
                        'sessions_24h': sessions_24h['count'] or 0,
                        'sessions_7d': sessions_7d['count'] or 0,
                        'top_computers': top_computers,
                        'hourly_distribution': hourly_distribution
                    }
                })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/quick-stats', methods=['GET'])
def get_quick_stats():
    """
    GET /api/dashboard/quick-stats
    Быстрая сводка (для заголовка дашборда).
    
    Returns минимальный набор данных для быстрого отображения.
    """
    try:
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                # Компьютеры онлайн/офлайн
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(is_online) as online
                    FROM computer
                """)
                comp_stats = cursor.fetchone()
                
                # Активные сессии
                cursor.execute("SELECT COUNT(*) as count FROM session WHERE status_id = 1")
                active_sessions = cursor.fetchone()
                
                # Новые сессии за час
                cursor.execute("""
                    SELECT COUNT(*) as count FROM session
                    WHERE start_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
                """)
                sessions_1h = cursor.fetchone()
                
                # Новые компьютеры за неделю
                cursor.execute("""
                    SELECT COUNT(*) as count FROM computer
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """)
                new_computers = cursor.fetchone()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'total_computers': comp_stats['total'] or 0,
                        'online_computers': comp_stats['online'] or 0,
                        'offline_computers': (comp_stats['total'] or 0) - (comp_stats['online'] or 0),
                        'active_sessions': active_sessions['count'] or 0,
                        'sessions_last_hour': sessions_1h['count'] or 0,
                        'new_computers_week': new_computers['count'] or 0
                    }
                })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/recent-activity', methods=['GET'])
def get_recent_activity():
    """
    GET /api/dashboard/recent-activity
    Получить недавнюю активность (для ленты событий).
    
    Query params:
        - limit: int (по умолчанию 20)
        - type: all|sessions|computers|users (по умолчанию all)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        activity_type = request.args.get('type', 'all')
        
        activities = []
        
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                # Последние сессии
                if activity_type in ('all', 'sessions'):
                    cursor.execute("""
                        SELECT 
                            'session' as type,
                            s.session_id as id,
                            s.start_time as timestamp,
                            c.hostname,
                            u.login,
                            st.status_name as status,
                            NULL as details
                        FROM session s
                        LEFT JOIN computer c ON s.computer_id = c.computer_id
                        LEFT JOIN user u ON c.user_id = u.user_id
                        LEFT JOIN status st ON s.status_id = st.status_id
                        ORDER BY s.start_time DESC
                        LIMIT %s
                    """, (limit,))
                    sessions = cursor.fetchall()
                    activities.extend(sessions)
                
                # Последние подключения компьютеров
                if activity_type in ('all', 'computers'):
                    cursor.execute("""
                        SELECT 
                            'computer_online' as type,
                            computer_id as id,
                            last_online as timestamp,
                            hostname,
                            NULL as login,
                            CASE WHEN is_online = 1 THEN 'Online' ELSE 'Offline' END as status,
                            NULL as details
                        FROM computer
                        ORDER BY last_online DESC
                        LIMIT %s
                    """, (limit,))
                    computers = cursor.fetchall()
                    activities.extend(computers)
        
        # Сортируем по времени
        activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        if len(activities) > limit:
            activities = activities[:limit]
        
        return jsonify({
            'success': True,
            'data': {
                'activities': activities,
                'total': len(activities)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
