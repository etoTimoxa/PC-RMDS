"""
Operating Systems routes - эндпоинты для работы с ОС
"""
from flask import Blueprint, request, jsonify

from ..services.mysql_service import MySQLService

os_bp = Blueprint('operating_systems', __name__)
mysql = MySQLService()


@os_bp.route('', methods=['GET'])
def get_operating_systems():
    """
    GET /api/operating-systems
    Получить список ОС.
    """
    try:
        os_list = mysql.get_operating_systems()
        
        return jsonify({
            'success': True,
            'data': os_list
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@os_bp.route('/families', methods=['GET'])
def get_os_families():
    """
    GET /api/operating-systems/families
    Получить семейства ОС.
    """
    try:
        families = mysql.get_os_families()
        
        return jsonify({
            'success': True,
            'data': families
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@os_bp.route('', methods=['POST'])
def create_operating_system():
    """
    POST /api/operating-systems
    Создать ОС.
    
    Body (JSON):
        - os_name: str (required)
        - os_version: str (required)
        - family_id: int (required)
        - os_build: str
        - os_architecture: str
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        required = ['os_name', 'os_version', 'family_id']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400
        
        os_id = mysql.create_operating_system(data)
        
        return jsonify({
            'success': True,
            'message': 'Operating system created successfully',
            'data': {
                'os_id': os_id
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


@os_bp.route('/<int:os_id>', methods=['PUT'])
def update_operating_system(os_id):
    """
    PUT /api/operating-systems/{id}
    Обновить ОС.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_operating_system(os_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Operating system not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Operating system updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@os_bp.route('/<int:os_id>', methods=['DELETE'])
def delete_operating_system(os_id):
    """
    DELETE /api/operating-systems/{id}
    Удалить ОС.
    """
    try:
        success = mysql.delete_operating_system(os_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Operating system not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Operating system deleted successfully'
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


@os_bp.route('/families', methods=['POST'])
def create_os_family():
    """
    POST /api/operating-systems/families
    Создать семейство ОС.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        required = ['family_name']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400
        
        family_id = mysql.create_os_family(data)
        
        return jsonify({
            'success': True,
            'message': 'OS family created successfully',
            'data': {
                'family_id': family_id
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


@os_bp.route('/families/<int:family_id>', methods=['PUT'])
def update_os_family(family_id):
    """
    PUT /api/operating-systems/families/{id}
    Обновить семейство ОС.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        success = mysql.update_os_family(family_id, data)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'OS family not found or no changes'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'OS family updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@os_bp.route('/families/<int:family_id>', methods=['DELETE'])
def delete_os_family(family_id):
    """
    DELETE /api/operating-systems/families/{id}
    Удалить семейство ОС.
    """
    try:
        success = mysql.delete_os_family(family_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'OS family not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'OS family deleted successfully'
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
