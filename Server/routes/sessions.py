"""
Sessions routes - эндпоинты для работы с сессиями
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from services.mysql_service import MySQLService

sessions_bp = Blueprint('sessions', __name__)
mysql = MySQLService()


@sessions_bp.route('', methods=['GET'])
def get_sessions():
    """
    GET /api/sessions
    Получить список сессий.
    
    Query params:
        - page: int
        - limit: int
        - computer_id: int
        - status_id: int
        - from: datetime (ISO format)
        - to: datetime (ISO format)
    """
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
    """
    GET /api/sessions/{id}
    Получить сессию по ID.
    """
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
    """
    GET /api/sessions/active
    Получить все активные сессии.
    """
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
    """
    GET /api/sessions/computer/{id}
    Получить сессии конкретного компьютера.
    """
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


@sessions_bp.route('/<int:session_id>', methods=['PUT'])
def update_session(session_id):
    """
    PUT /api/sessions/{id}
    Обновить сессию.
    
    Body (JSON):
        - status_id: int
        - end_time: datetime
        - last_activity: datetime
        - json_sent_count: int
        - error_count: int
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_session(session_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Session not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Session updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('', methods=['POST'])
def create_session():
    """
    POST /api/sessions
    Создать новую сессию
    """
    try:
        data = request.get_json()
        
        required_fields = ['computer_id', 'user_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400
                
        session_id = mysql.execute("""
            INSERT INTO sessions (computer_id, user_id, start_time, status_id, created_at)
            VALUES (%s, %s, NOW(), 1, NOW())
        """, (data['computer_id'], data['user_id']))
        
        return jsonify({
            'success': True,
            'message': 'Сессия успешно создана',
            'data': {
                'session_id': session_id
            }
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sessions_bp.route('/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    """
    DELETE /api/sessions/{id}
    Удалить сессию.
    """
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
