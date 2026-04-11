"""
Users routes - эндпоинты для работы с пользователями
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from ..services.mysql_service import MySQLService

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


# Роли
@users_bp.route('/roles', methods=['GET'])
def get_roles():
    """
    GET /api/users/roles
    Получить список ролей.
    """
    try:
        roles = mysql.get_roles()
        
        return jsonify({
            'success': True,
            'data': roles
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/roles/<int:role_id>', methods=['GET'])
def get_role(role_id):
    """
    GET /api/users/roles/{id}
    Получить роль по ID.
    """
    try:
        role = mysql.get_role_by_id(role_id)
        
        if not role:
            return jsonify({
                'success': False,
                'error': 'Role not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': role
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@users_bp.route('/roles/<int:role_id>/users', methods=['GET'])
def get_role_users(role_id):
    """
    GET /api/users/roles/{id}/users
    Получить пользователей с этой ролью.
    """
    try:
        users = mysql.get_role_users(role_id)
        
        return jsonify({
            'success': True,
            'data': {
                'role_id': role_id,
                'users': users
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
