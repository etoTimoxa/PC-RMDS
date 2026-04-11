"""
IP Addresses routes - эндпоинты для работы с IP адресами
"""
from flask import Blueprint, request, jsonify

from ..services.mysql_service import MySQLService

ip_bp = Blueprint('ip_addresses', __name__)
mysql = MySQLService()


@ip_bp.route('', methods=['GET'])
def get_ip_history():
    """
    GET /api/ip-addresses
    Получить историю IP адресов.
    
    Query params:
        - page: int
        - limit: int
        - computer_id: int
    """
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        computer_id = request.args.get('computer_id', type=int)
        
        result = mysql.get_ip_history(
            page=page,
            limit=limit,
            computer_id=computer_id
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


@ip_bp.route('/current', methods=['GET'])
def get_current_ips():
    """
    GET /api/ip-addresses/current
    Получить текущие IP всех компьютеров.
    """
    try:
        ips = mysql.get_current_ips()
        
        return jsonify({
            'success': True,
            'data': {
                'addresses': ips,
                'total': len(ips)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ip_bp.route('', methods=['POST'])
def create_ip_address():
    """
    POST /api/ip-addresses
    Создать IP адрес.
    
    Body (JSON):
        - computer_id: int (required)
        - ip_address: str (required)
        - subnet_mask: str
        - gateway: str
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        required = ['computer_id', 'ip_address']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400
        
        ip_id = mysql.create_ip_address(data)
        
        return jsonify({
            'success': True,
            'message': 'IP address created successfully',
            'data': {
                'ip_id': ip_id
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


@ip_bp.route('/<int:ip_id>', methods=['PUT'])
def update_ip_address(ip_id):
    """
    PUT /api/ip-addresses/{id}
    Обновить IP адрес.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_ip_address(ip_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'IP address not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'IP address updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ip_bp.route('/<int:ip_id>', methods=['DELETE'])
def delete_ip_address(ip_id):
    """
    DELETE /api/ip-addresses/{id}
    Удалить IP адрес.
    """
    try:
        success = mysql.delete_ip_address(ip_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'IP address not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'IP address deleted successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
