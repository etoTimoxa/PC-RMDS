"""
Маршруты для работы со статусами
"""
from flask import Blueprint, request, jsonify
from services.mysql_service import MySQLService

statuses_bp = Blueprint('statuses', __name__)
db = MySQLService()


@statuses_bp.route('', methods=['GET'])
def get_statuses():
    """Получить список всех статусов"""
    status_type = request.args.get('type')
    
    query = "SELECT * FROM status"
    params = []
    
    if status_type:
        query += " WHERE status_type = %s"
        params.append(status_type)
    
    statuses = db.fetch_all(query, params)
    return jsonify({
        'success': True,
        'data': statuses
    })


@statuses_bp.route('/<int:status_id>', methods=['GET'])
def get_status(status_id):
    """Получить статус по ID"""
    status = db.fetch_one("SELECT * FROM status WHERE status_id = %s", (status_id,))
    
    if not status:
        return jsonify({
            'success': False,
            'error': 'Статус не найден'
        }), 404
        
    return jsonify({
        'success': True,
        'data': status
    })


@statuses_bp.route('', methods=['POST'])
def create_status():
    """Создать новый статус"""
    data = request.get_json()
    
    required_fields = ['status_name', 'status_type']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'success': False,
                'error': f'Отсутствует обязательное поле: {field}'
            }), 400
    
    status_id = db.execute("""
        INSERT INTO status (status_name, status_type, description)
        VALUES (%s, %s, %s)
    """, (
        data['status_name'],
        data.get('status_type', 'general'),
        data.get('description')
    ))
    
    return jsonify({
        'success': True,
        'data': {
            'status_id': status_id
        }
    }), 201


@statuses_bp.route('/<int:status_id>', methods=['PUT'])
def update_status(status_id):
    """Обновить статус"""
    data = request.get_json()
    
    updates = []
    params = []
    
    if 'status_name' in data:
        updates.append("status_name = %s")
        params.append(data['status_name'])
    if 'status_type' in data:
        updates.append("status_type = %s")
        params.append(data['status_type'])
    if 'description' in data:
        updates.append("description = %s")
        params.append(data['description'])
    
    if not updates:
        return jsonify({
            'success': False,
            'error': 'Нет полей для обновления'
        }), 400
    
    params.append(status_id)
    
    db.execute(f"""
        UPDATE status SET {', '.join(updates)}
        WHERE status_id = %s
    """, params)
    
    return jsonify({
        'success': True
    })


@statuses_bp.route('/<int:status_id>', methods=['DELETE'])
def delete_status(status_id):
    """Удалить статус"""
    db.execute("DELETE FROM status WHERE status_id = %s", (status_id,))
    return jsonify({
        'success': True
    })