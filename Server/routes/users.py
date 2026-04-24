"""
Users routes - эндпоинты для работы с пользователями
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from services.mysql_service import MySQLService

users_bp = Blueprint('users', __name__)
mysql = MySQLService()


@users_bp.route('', methods=['GET'])
def get_users():
    """
    GET /api/users
    Получить список пользователей.
    
    Query params:
        - page: int
        - limit: int
        - role_id: int
        - search: str
        - is_active: bool
    """
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        role_id = request.args.get('role_id', type=int)
        search = request.args.get('search')
        is_active = request.args.get('is_active')
        
        if is_active is not None:
            is_active = is_active.lower() in ('true', '1', 'yes')
        
        result = mysql.get_users(
            page=page,
            limit=limit,
            role_id=role_id,
            search=search,
            is_active=is_active
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


@users_bp.route('/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """
    GET /api/users/{id}
    Получить пользователя по ID.
    """
    try:
        user = mysql.get_user_by_id(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': user
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/<int:user_id>/computers', methods=['GET'])
def get_user_computers(user_id):
    """
    GET /api/users/{id}/computers
    Получить компьютеры пользователя.
    """
    try:
        computers = mysql.get_user_computers(user_id)
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'computers': computers
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('', methods=['POST'])
def create_user():
    """
    POST /api/users
    Создать пользователя.
    
    Body (JSON):
        - login: str (required)
        - password: str (required)
        - full_name: str
        - role_id: int (required)
        - is_active: bool
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        required = ['login', 'password', 'role_id']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400
        
        user_id = mysql.create_user(data)
        
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'data': {
                'user_id': user_id
            }
        }), 201
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """
    PUT /api/users/{id}
    Обновить пользователя.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_user(user_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'User not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'User updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """
    DELETE /api/users/{id}
    Удалить пользователя.
    """
    try:
        success = mysql.delete_user(user_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/<int:user_id>/roles', methods=['GET'])
def get_user_roles(user_id):
    """
    GET /api/users/{id}/roles
    Получить роли пользователя.
    """
    try:
        roles = mysql.get_user_roles(user_id)
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'roles': roles
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/<int:user_id>/sessions', methods=['GET'])
def get_user_sessions(user_id):
    """
    GET /api/users/{id}/sessions
    Получить сессии пользователя.
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        sessions = mysql.get_user_sessions(user_id, limit=limit)
        
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


@users_bp.route('/<int:user_id>/block', methods=['POST'])
def block_user(user_id):
    """
    POST /api/users/{id}/block
    Блокировать/разблокировать пользователя.
    """
    try:
        data = request.get_json()
        
        if not data or 'is_active' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing is_active parameter'
            }), 400
        
        is_active = int(data.get('is_active', 1))
        
        success = mysql.update_user(user_id, {'is_active': is_active})
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Если пользователь заблокирован - закрываем все его активные сессии
        if is_active == 0:
            mysql.close_all_user_sessions(user_id)
        
        return jsonify({
            'success': True,
            'message': 'User status updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/<int:user_id>/reset-password', methods=['POST'])
def reset_user_password(user_id):
    """
    POST /api/users/{id}/reset-password
    Сброс пароля пользователя администратором
    """
    try:
        user = mysql.fetch_one(
            "SELECT user_id, login, is_active FROM user WHERE user_id = %s",
            (user_id,)
        )
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Пользователь не найден'
            }), 404

        # Устанавливаем флаг обязательной смены пароля при следующем входе
        mysql.execute("""
            UPDATE user 
            SET require_password_change = 1 
            WHERE user_id = %s
        """, (user_id,))

        return jsonify({
            'success': True,
            'message': 'Пароль сброшен. При следующем входе пользователь должен будет сменить пароль'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
