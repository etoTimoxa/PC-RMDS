"""
Roles routes - эндпоинты для работы с ролями
"""
from flask import Blueprint, request, jsonify

from services.mysql_service import MySQLService

roles_bp = Blueprint('roles', __name__)
mysql = MySQLService()


@roles_bp.route('', methods=['GET'])
def get_roles():
    """
    GET /api/roles
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


@roles_bp.route('/<int:role_id>', methods=['GET'])
def get_role(role_id):
    """
    GET /api/roles/{id}
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


@roles_bp.route('/<int:role_id>/users', methods=['GET'])
def get_role_users(role_id):
    """
    GET /api/roles/{id}/users
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


@roles_bp.route('', methods=['POST'])
def create_role():
    """
    POST /api/roles
    Создать роль.
    
    Body (JSON):
        - role_name: str (required)
        - description: str
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        required = ['role_name']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400
        
        role_id = mysql.create_role(data)
        
        return jsonify({
            'success': True,
            'message': 'Role created successfully',
            'data': {
                'role_id': role_id
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


@roles_bp.route('/<int:role_id>', methods=['PUT'])
def update_role(role_id):
    """
    PUT /api/roles/{id}
    Обновить роль.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_role(role_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Role not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Role updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@roles_bp.route('/<int:role_id>', methods=['DELETE'])
def delete_role(role_id):
    """
    DELETE /api/roles/{id}
    Удалить роль.
    """
    try:
        success = mysql.delete_role(role_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Role not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Role deleted successfully'
        })
        
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
