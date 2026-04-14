"""
Computers routes - эндпоинты для работы с компьютерами
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import hashlib

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
        
        required_fields = ['user_id', 'hardware_hash', 'hostname', 'mac_address']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400
                
        user_id = data['user_id']
        hardware_hash = data['hardware_hash']
        hostname = data['hostname']
        mac_address = data['mac_address']
        force_rebind = data.get('force_rebind', False)
        
        cpu_model = data.get('cpu_model', hardware_hash[:100])
        ram_total = data.get('ram_total_gb', 0)
        storage_total = data.get('storage_total_gb', 0)
        
        # 1. Ищем или создаем конфигурацию железа
        existing_config = mysql.fetch_one(
            "SELECT config_id FROM hardware_config WHERE cpu_model = %s",
            (hardware_hash,)
        )
        
        if existing_config:
            config_id = existing_config['config_id']
        else:
            config_id = mysql.execute("""
                INSERT INTO hardware_config (cpu_model, cpu_cores, ram_total, storage_total, detected_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (hardware_hash, None, ram_total, storage_total))
        
        # 2. Ищем компьютер по MAC адресу
        existing_computer = mysql.fetch_one(
            "SELECT computer_id, user_id FROM computer WHERE mac_address = %s",
            (mac_address,)
        )
        
        if existing_computer:
            computer_id = existing_computer['computer_id']
            
            if existing_computer['user_id'] != user_id:
                if not force_rebind:
                    other_user = mysql.fetch_one(
                        "SELECT login FROM user WHERE user_id = %s",
                        (existing_computer['user_id'],)
                    )
                    return jsonify({
                        'success': False,
                        'error': 'Этот компьютер уже привязан к другому пользователю',
                        'data': {
                            'already_bound': True,
                            'other_user_login': other_user['login'] if other_user else 'Unknown'
                        }
                    }), 409
                else:
                    mysql.execute("""
                        UPDATE computer 
                        SET user_id = %s, hostname = %s, hardware_config_id = %s, 
                            is_online = 1, last_online = NOW()
                        WHERE computer_id = %s
                    """, (user_id, hostname, config_id, computer_id))
            else:
                mysql.execute("""
                    UPDATE computer 
                    SET hostname = %s, hardware_config_id = %s, is_online = 1, last_online = NOW()
                    WHERE computer_id = %s
                """, (hostname, config_id, computer_id))
        else:
            computer_id = mysql.execute("""
                INSERT INTO computer (user_id, hardware_config_id, hostname, mac_address, 
                                     computer_type, is_online, created_at, last_online)
                VALUES (%s, %s, %s, %s, 'client', 1, NOW(), NOW())
            """, (user_id, config_id, hostname, mac_address))
        
        # 3. Добавляем IP адрес
        ip_address = data.get('ip_address')
        if ip_address:
            mysql.execute("""
                INSERT INTO ip_address (computer_id, ip_address, detected_at)
                VALUES (%s, %s, NOW())
            """, (computer_id, ip_address))
        
        return jsonify({
            'success': True,
            'message': 'Компьютер успешно зарегистрирован',
            'data': {
                'computer_id': computer_id,
                'user_id': user_id,
                'hardware_config_id': config_id,
                'hostname': hostname,
                'mac_address': mac_address,
                'is_online': 1,
                'is_new': existing_computer is None,
                'hardware_changed': existing_config is None
            }
        })
        
    except Exception as e:
        print(f"Ошибка регистрации компьютера: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('', methods=['GET'])
def get_computers():
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


@computers_bp.route('/<int:computer_id>', methods=['GET'])
def get_computer(computer_id):
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


@computers_bp.route('/<int:computer_id>/status', methods=['PUT'])
def update_computer_status(computer_id):
    try:
        data = request.get_json()
        
        if not data or 'is_online' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует обязательное поле is_online'
            }), 400
            
        is_online = bool(data['is_online'])
        session_id = data.get('session_id')
        
        mysql.execute("""
            UPDATE computer 
            SET is_online = %s, last_online = NOW()
            WHERE computer_id = %s
        """, (is_online, computer_id))
        
        return jsonify({
            'success': True,
            'message': 'Статус компьютера обновлен'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/sessions', methods=['GET'])
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


@computers_bp.route('/<int:computer_id>/ip-addresses', methods=['GET'])
def get_computer_ip_addresses(computer_id):
    try:
        ip_addresses = mysql.get_computer_ip_history(computer_id)
        
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


@computers_bp.route('/<int:computer_id>', methods=['PUT'])
def update_computer(computer_id):
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


@computers_bp.route('/<int:computer_id>', methods=['DELETE'])
def delete_computer(computer_id):
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