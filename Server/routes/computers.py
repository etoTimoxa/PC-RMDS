"""
Computers routes - эндпоинты для работы с компьютерами
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from services.mysql_service import MySQLService

computers_bp = Blueprint('computers', __name__)
mysql = MySQLService()


@computers_bp.route('/register', methods=['POST'])
def register_computer():
    """
    POST /api/computers/register
    Регистрация компьютера для пользователя
    """
    try:
        data = request.get_json()
        
        required_fields = ['user_id', 'hardware_id', 'hostname']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400
                
        user_id = data['user_id']
        hardware_id = data['hardware_id']
        hostname = data['hostname']
        force_rebind = data.get('force_rebind', False)
        
        # Проверяем существует ли уже компьютер с таким hardware_id
        existing = mysql.fetch_one(
            "SELECT computer_id, user_id, is_active FROM computers WHERE hardware_id = %s",
            (hardware_id,)
        )
        
        if existing:
            if not force_rebind and existing['user_id'] != user_id:
                return jsonify({
                    'success': False,
                    'error': 'Этот компьютер уже привязан к другому пользователю'
                }), 409
            
            # Обновляем существующий компьютер
            computer_id = existing['computer_id']
            mysql.execute("""
                UPDATE computers 
                SET user_id = %s, hostname = %s, last_seen = NOW(), is_online = 1
                WHERE computer_id = %s
            """, (user_id, hostname, computer_id))
        else:
            # Создаем новый компьютер
            computer_id = mysql.execute("""
                INSERT INTO computers (user_id, hardware_id, hostname, computer_type, is_online, is_active, created_at, last_seen)
                VALUES (%s, %s, %s, 'client', 1, 1, NOW(), NOW())
            """, (user_id, hardware_id, hostname))
        
        computer = mysql.get_computer_by_id(computer_id)
        
        return jsonify({
            'success': True,
            'message': 'Компьютер успешно зарегистрирован',
            'data': computer
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('', methods=['GET'])
def get_computers():
    """
    GET /api/computers
    Получить список компьютеров с фильтрами и пагинацией.
    
    Query params:
        - page: int (по умолчанию 1)
        - limit: int (по умолчанию 20)
        - status: online|offline|all (по умолчанию all)
        - type: client|admin|all (по умолчанию all)
        - search: str (поиск по hostname)
        - user_id: int
        - os_id: int
    """
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        status = request.args.get('status', 'all')
        computer_type = request.args.get('type', 'all')
        search = request.args.get('search')
        user_id = request.args.get('user_id', type=int)
        os_id = request.args.get('os_id', type=int)
        
        result = mysql.get_computers(
            page=page,
            limit=limit,
            status=status,
            computer_type=computer_type,
            search=search,
            user_id=user_id,
            os_id=os_id
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


@computers_bp.route('/<int:computer_id>/hardware', methods=['GET'])
def get_computer_hardware(computer_id):
    """
    GET /api/computers/{id}/hardware
    Получить информацию о железе компьютера.
    """
    try:
        hardware = mysql.get_hardware_by_computer_id(computer_id)
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'hardware': hardware
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/ip-addresses', methods=['GET'])
def get_computer_ip_addresses(computer_id):
    """
    GET /api/computers/{id}/ip-addresses
    Получить IP адреса компьютера.
    """
    try:
        ip_addresses = mysql.get_ip_addresses_by_computer_id(computer_id)
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'ip_addresses': ip_addresses
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/operating-system', methods=['GET'])
def get_computer_operating_system(computer_id):
    """
    GET /api/computers/{id}/operating-system
    Получить информацию об операционной системе компьютера.
    """
    try:
        os = mysql.get_operating_system_by_computer_id(computer_id)
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'operating_system': os
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@computers_bp.route('/<int:computer_id>', methods=['GET'])
def get_computer(computer_id):
    """
    GET /api/computers/{id}
    Получить детали компьютера по ID.
    """
    try:
        computer = mysql.get_computer_by_id(computer_id)
        
        if not computer:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': computer
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/sessions', methods=['GET'])
def get_computer_sessions(computer_id):
    """
    GET /api/computers/{id}/sessions
    Получить историю сессий компьютера.
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


@computers_bp.route('/<int:computer_id>/ip-history', methods=['GET'])
def get_computer_ip_history(computer_id):
    """
    GET /api/computers/{id}/ip-history
    Получить историю IP адресов компьютера.
    """
    try:
        history = mysql.get_computer_ip_history(computer_id)
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'ip_history': history
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>', methods=['PUT'])
def update_computer(computer_id):
    """
    PUT /api/computers/{id}
    Обновить данные компьютера.
    
    Body (JSON):
        - hostname: str
        - description: str
        - computer_type: client|admin
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_computer(computer_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Computer not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Computer updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/status', methods=['PUT'])
def update_computer_status(computer_id):
    """
    PUT /api/computers/{id}/status
    Обновить статус онлайн/оффлайн компьютера
    """
    try:
        data = request.get_json()
        
        if not data or 'is_online' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует обязательное поле is_online'
            }), 400
            
        is_online = bool(data['is_online'])
        session_id = data.get('session_id')
        
        success = mysql.execute("""
            UPDATE computer 
            SET is_online = %s, last_online = NOW()
            WHERE computer_id = %s
        """, (is_online, computer_id))
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Компьютер не найден'
            }), 404
            
        return jsonify({
            'success': True,
            'message': 'Статус компьютера обновлен'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>', methods=['DELETE'])
def delete_computer(computer_id):
    """
    DELETE /api/computers/{id}
    Удалить компьютер.
    """
    try:
        success = mysql.delete_computer(computer_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Computer deleted successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
