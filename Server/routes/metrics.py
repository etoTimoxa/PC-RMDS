"""
Metrics routes - эндпоинты для работы с метриками из S3
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

from services.mysql_service import MySQLService
from services.cloud_service import CloudService

metrics_bp = Blueprint('metrics', __name__)
mysql = MySQLService()
cloud = CloudService()


@metrics_bp.route('/full-period', methods=['GET'])
def get_full_period_files():
    """
    GET /api/metrics/full-period
    Получить все записи из файлов за указанный период (несколько дней).
    
    Query params:
        - computer_id: int - ID компьютера (либо этот параметр)
        - hostname: string - Название компьютера напрямую (либо этот параметр)
        - from: string (required) - Начальная дата в формате YYYY-MM-DD
        - to: string (required) - Конечная дата в формате YYYY-MM-DD
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        hostname_param = request.args.get('hostname')
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')
        
        if not computer_id and not hostname_param:
            return jsonify({
                'success': False,
                'error': 'Either computer_id or hostname parameter is required'
            }), 400
        
        if not from_date_str or not to_date_str:
            return jsonify({
                'success': False,
                'error': 'Both "from" and "to" date parameters are required (format YYYY-MM-DD)'
            }), 400
        
        hostname = hostname_param
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found with specified computer_id'
                }), 404
        
        period_data = cloud.get_full_period_files(hostname, from_date_str, to_date_str)
        
        response_data = {
            **period_data
        }
        if computer_id:
            response_data['computer_id'] = computer_id
        
        return jsonify({
            'success': period_data.get('success', True),
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/upload', methods=['POST'])
def upload_metrics_file():
    """
    POST /api/metrics/upload
    Отправка готового файла метрик на облачное хранилище S3
    Принимает файл в формате multipart/form-data
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Файл не был передан в запросе'
            }), 400

        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'Не выбран файл для загрузки'
            }), 400

        # Загружаем файл напрямую в облако
        result = cloud.upload_metrics_file(file)

        return jsonify({
            'success': True,
            'message': 'Файл успешно загружен в облако',
            'data': result
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/average', methods=['GET'])
def get_average_performance():
    """
    GET /api/metrics/average
    Получить средние показатели производительности за период.
    
    Query params:
        - computer_id: int - ID компьютера (либо этот параметр)
        - hostname: string - Название компьютера напрямую (либо этот параметр)
        - from: string (required) - Начальная дата в формате YYYY-MM-DD
        - to: string (required) - Конечная дата в формате YYYY-MM-DD
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        hostname_param = request.args.get('hostname')
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')
        
        if not computer_id and not hostname_param:
            return jsonify({
                'success': False,
                'error': 'Either computer_id or hostname parameter is required'
            }), 400
        
        if not from_date_str or not to_date_str:
            return jsonify({
                'success': False,
                'error': 'Both "from" and "to" date parameters are required (format YYYY-MM-DD)'
            }), 400
        
        hostname = hostname_param
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found with specified computer_id'
                }), 404
        
        average_data = cloud.get_average_performance(hostname, from_date_str, to_date_str)
        
        response_data = {
            **average_data
        }
        if computer_id:
            response_data['computer_id'] = computer_id
        
        return jsonify({
            'success': average_data.get('success', True),
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/performance', methods=['GET'])
def get_all_performance():
    """
    GET /api/metrics/performance
    Получить ВСЕ показатели производительности за период (каждая точка отдельно).
    
    Query params:
        - computer_id: int - ID компьютера (либо этот параметр)
        - hostname: string - Название компьютера напрямую (либо этот параметр)
        - from: string (required) - Начальная дата в формате YYYY-MM-DD
        - to: string (required) - Конечная дата в формате YYYY-MM-DD
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        hostname_param = request.args.get('hostname')
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')
        
        if not computer_id and not hostname_param:
            return jsonify({
                'success': False,
                'error': 'Either computer_id or hostname parameter is required'
            }), 400
        
        if not from_date_str or not to_date_str:
            return jsonify({
                'success': False,
                'error': 'Both "from" and "to" date parameters are required (format YYYY-MM-DD)'
            }), 400
        
        hostname = hostname_param
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found with specified computer_id'
                }), 404
        
        performance_data = cloud.get_all_performance(hostname, from_date_str, to_date_str)
        
        response_data = {
            **performance_data
        }
        if computer_id:
            response_data['computer_id'] = computer_id
        
        return jsonify({
            'success': performance_data.get('success', True),
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/events', methods=['GET'])
def get_all_events():
    """
    GET /api/metrics/events
    Получить ВСЕ события за период.
    
    Query params:
        - computer_id: int - ID компьютера (либо этот параметр)
        - hostname: string - Название компьютера напрямую (либо этот параметр)
        - from: string (required) - Начальная дата в формате YYYY-MM-DD
        - to: string (required) - Конечная дата в формате YYYY-MM-DD
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        hostname_param = request.args.get('hostname')
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')
        
        if not computer_id and not hostname_param:
            return jsonify({
                'success': False,
                'error': 'Either computer_id or hostname parameter is required'
            }), 400
        
        if not from_date_str or not to_date_str:
            return jsonify({
                'success': False,
                'error': 'Both "from" and "to" date parameters are required (format YYYY-MM-DD)'
            }), 400
        
        hostname = hostname_param
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found with specified computer_id'
                }), 404
        
        events_data = cloud.get_all_events(hostname, from_date_str, to_date_str)
        
        response_data = {
            **events_data
        }
        if computer_id:
            response_data['computer_id'] = computer_id
        
        return jsonify({
            'success': events_data.get('success', True),
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/events/statistics', methods=['GET'])
def get_events_statistics():
    """
    GET /api/metrics/events/statistics
    Получить статистику по количеству каждого типа событий за период.
    
    Query params:
        - computer_id: int - ID компьютера (либо этот параметр)
        - hostname: string - Название компьютера напрямую (либо этот параметр)
        - from: string (required) - Начальная дата в формате YYYY-MM-DD
        - to: string (required) - Конечная дата в формате YYYY-MM-DD
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        hostname_param = request.args.get('hostname')
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')
        
        if not computer_id and not hostname_param:
            return jsonify({
                'success': False,
                'error': 'Either computer_id or hostname parameter is required'
            }), 400
        
        if not from_date_str or not to_date_str:
            return jsonify({
                'success': False,
                'error': 'Both "from" and "to" date parameters are required (format YYYY-MM-DD)'
            }), 400
        
        hostname = hostname_param
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found with specified computer_id'
                }), 404
        
        stats_data = cloud.get_events_statistics(hostname, from_date_str, to_date_str)
        
        response_data = {
            **stats_data
        }
        if computer_id:
            response_data['computer_id'] = computer_id
        
        return jsonify({
            'success': stats_data.get('success', True),
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/anomalies', methods=['GET'])
def get_anomalies():
    """
    GET /api/metrics/anomalies
    Получить аномалии (высокая нагрузка CPU/RAM) за период.
    
    Query params:
        - computer_id: int - ID компьютера (либо этот параметр)
        - hostname: string - Название компьютера напрямую (либо этот параметр)
        - from: string (required) - Начальная дата в формате YYYY-MM-DD
        - to: string (required) - Конечная дата в формате YYYY-MM-DD
        - cpu_threshold: float (по умолчанию 90.0) - Порог CPU в процентах
        - ram_threshold: float (по умолчанию 90.0) - Порог RAM в процентах
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        hostname_param = request.args.get('hostname')
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')
        cpu_threshold = request.args.get('cpu_threshold', 90.0, type=float)
        ram_threshold = request.args.get('ram_threshold', 90.0, type=float)
        
        if not computer_id and not hostname_param:
            return jsonify({
                'success': False,
                'error': 'Either computer_id or hostname parameter is required'
            }), 400
        
        if not from_date_str or not to_date_str:
            return jsonify({
                'success': False,
                'error': 'Both "from" and "to" date parameters are required (format YYYY-MM-DD)'
            }), 400
        
        hostname = hostname_param
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found with specified computer_id'
                }), 404
        
        anomalies_data = cloud.get_anomalies(hostname, from_date_str, to_date_str, cpu_threshold, ram_threshold)
        
        response_data = {
            **anomalies_data
        }
        if computer_id:
            response_data['computer_id'] = computer_id
        
        return jsonify({
            'success': anomalies_data.get('success', True),
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
