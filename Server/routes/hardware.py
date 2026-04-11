"""
Hardware routes - эндпоинты для работы с конфигурациями железа
"""
from flask import Blueprint, request, jsonify

from ..services.mysql_service import MySQLService

hardware_bp = Blueprint('hardware', __name__)
mysql = MySQLService()


@hardware_bp.route('', methods=['GET'])
def get_hardware_configs():
    """
    GET /api/hardware
    Получить список конфигураций железа.
    
    Query params:
        - page: int
        - limit: int
    """
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        
        result = mysql.get_hardware_configs(page=page, limit=limit)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hardware_bp.route('/<int:config_id>', methods=['GET'])
def get_hardware_config(config_id):
    """
    GET /api/hardware/{id}
    Получить конфигурацию железа по ID.
    """
    try:
        config = mysql.get_hardware_config_by_id(config_id)
        
        if not config:
            return jsonify({
                'success': False,
                'error': 'Hardware config not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': config
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hardware_bp.route('/unique', methods=['GET'])
def get_unique_configs():
    """
    GET /api/hardware/unique
    Получить уникальные конфигурации железа.
    """
    try:
        configs = mysql.get_unique_hardware_configs()
        
        return jsonify({
            'success': True,
            'data': {
                'configs': configs,
                'total': len(configs)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hardware_bp.route('', methods=['POST'])
def create_hardware_config():
    """
    POST /api/hardware
    Создать конфигурацию железа.
    
    Body (JSON):
        - cpu_model: str (required)
        - cpu_cores: int
        - ram_total: float
        - storage_total: float
        - gpu_model: str
        - motherboard: str
        - bios_version: str
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        required = ['cpu_model']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400
        
        config_id = mysql.create_hardware_config(data)
        
        return jsonify({
            'success': True,
            'message': 'Hardware config created successfully',
            'data': {
                'config_id': config_id
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


@hardware_bp.route('/<int:config_id>', methods=['PUT'])
def update_hardware_config(config_id):
    """
    PUT /api/hardware/{id}
    Обновить конфигурацию железа.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_hardware_config(config_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Hardware config not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Hardware config updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hardware_bp.route('/<int:config_id>', methods=['DELETE'])
def delete_hardware_config(config_id):
    """
    DELETE /api/hardware/{id}
    Удалить конфигурацию железа.
    """
    try:
        success = mysql.delete_hardware_config(config_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Hardware config not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Hardware config deleted successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
