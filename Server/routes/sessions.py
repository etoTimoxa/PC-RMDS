"""
Sessions routes - эндпоинты для работы с сессиями
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from services.mysql_service import MySQLService

sessions_bp = Blueprint('sessions', __name__)
mysql = MySQLService()


@sessions_bp.route('', methods=['POST'])
def create_session():
    """
    POST /api/sessions
    Создать новую сессию
    """
    try:
        data = request.get_json()
        
        if not data or 'computer_id' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует обязательное поле: computer_id'
            }), 400
        
        computer_id = data['computer_id']
        user_id = data.get('user_id')
        session_token = data.get('session_token')
        
        if not session_token:
            session_token = f"session_{computer_id}_{int(datetime.now().timestamp())}"
        
        # Проверяем уникальность токена
        existing = mysql.fetch_one(
            "SELECT session_id FROM session WHERE session_token = %s",
            (session_token,)
        )
        
        if existing:
            session_token = f"{session_token}_{int(datetime.now().timestamp())}"
        
        # Вставляем сессию (с user_id если передан)
        if user_id:
            session_id = mysql.execute("""
                INSERT INTO session (computer_id, user_id, session_token, start_time, last_activity, status_id, json_sent_count, error_count, created_at)
                VALUES (%s, %s, %s, NOW(), NOW(), 1, 0, 0, NOW())
            """, (computer_id, user_id, session_token))
        else:
            session_id = mysql.execute("""
                INSERT INTO session (computer_id, session_token, start_time, last_activity, status_id, json_sent_count, error_count, created_at)
                VALUES (%s, %s, NOW(), NOW(), 1, 0, 0, NOW())
            """, (computer_id, session_token))
        
        # Обновляем статус компьютера на онлайн
        mysql.execute("""
            UPDATE computer SET is_online = 1, last_online = NOW()
            WHERE computer_id = %s
        """, (computer_id,))
        
        return jsonify({
            'success': True,
            'message': 'Сессия успешно создана',
            'data': {
                'session_id': session_id,
                'session_token': session_token,
                'computer_id': computer_id,
                'user_id': user_id,
                'status_id': 1
            }
        }), 201
        
    except Exception as e:
        print(f"Ошибка создания сессии: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('', methods=['GET'])
def get_sessions():
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        computer_id = request.args.get('computer_id', type=int)
        status_id = request.args.get('status_id', type=int)
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        
        from_date = None
        to_date = None
        
        if from_str:
            try:
                from_date = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        if to_str:
            try:
                to_date = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        result = mysql.get_sessions(
            page=page,
            limit=limit,
            computer_id=computer_id,
            status_id=status_id,
            from_date=from_date,
            to_date=to_date
        )
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/<int:session_id>', methods=['GET'])
def get_session(session_id):
    try:
        session = mysql.get_session_by_id(session_id)
        
        if not session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': session
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/active', methods=['GET'])
def get_active_sessions():
    try:
        sessions = mysql.get_active_sessions()
        
        return jsonify({
            'success': True,
            'data': {
                'active_sessions': sessions,
                'count': len(sessions)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/computer/<int:computer_id>', methods=['GET'])
def get_computer_sessions(computer_id):
    try:
        limit = request.args.get('limit', 20, type=int)
        sessions = mysql.get_computer_sessions(computer_id, limit=limit)
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'sessions': sessions
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/user/<int:user_id>', methods=['GET'])
def get_user_sessions(user_id):
    """Получить сессии пользователя"""
    try:
        limit = request.args.get('limit', 20, type=int)
        
        sessions = mysql.fetch_all("""
            SELECT s.*, c.hostname, st.status_name
            FROM session s
            LEFT JOIN computer c ON s.computer_id = c.computer_id
            LEFT JOIN status st ON s.status_id = st.status_id
            WHERE s.user_id = %s
            ORDER BY s.start_time DESC
            LIMIT %s
        """, (user_id, limit))
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'sessions': sessions
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/<int:session_id>', methods=['PUT'])
def update_session(session_id):
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        allowed_fields = ['status_id', 'end_time', 'last_activity', 'json_sent_count', 'error_count']
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_data:
            return jsonify({
                'success': False,
                'error': 'No valid fields to update'
            }), 400
        
        success = mysql.update_session(session_id, update_data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Session not found or no changes'
            }), 404
        
        # Если сессия закрывается, обновляем статус компьютера
        if update_data.get('status_id') == 2:
            session = mysql.get_session_by_id(session_id)
            if session and session.get('computer_id'):
                active_sessions = mysql.fetch_all("""
                    SELECT session_id FROM session 
                    WHERE computer_id = %s AND status_id = 1 AND session_id != %s
                """, (session['computer_id'], session_id))
                
                if not active_sessions:
                    mysql.execute("""
                        UPDATE computer SET is_online = 0
                        WHERE computer_id = %s
                    """, (session['computer_id'],))
        
        return jsonify({
            'success': True,
            'message': 'Session updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    try:
        success = mysql.delete_session(session_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Session deleted successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500