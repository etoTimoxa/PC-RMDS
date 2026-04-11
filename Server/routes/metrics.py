"""
Metrics routes - эндпоинты для работы с метриками из S3
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

from ..services.mysql_service import MySQLService
from ..services.cloud_service import CloudService

metrics_bp = Blueprint('metrics', __name__)
mysql = MySQLService()
cloud = CloudService()


@metrics_bp.route('', methods=['GET'])
def get_metrics():
    """
    GET /api/metrics
    Получить метрики за период.
    
    Query params:
        - computer_id: int (required) - ID компьютера
        - from: datetime (ISO format) - начало периода
        - to: datetime (ISO format) - конец периода
        - type: cpu|ram|disk|network|all (по умолчанию all)
        - resolution: raw|5min|30min (по умолчанию raw)
        - limit: int (по умолчанию 1000)
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        if not computer_id:
            return jsonify({
                'success': False,
                'error': 'computer_id is required'
            }), 400
        
        # Получаем hostname по ID
        hostname = mysql.get_computer_hostname(computer_id)
        if not hostname:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        # Параметры
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        metric_type = request.args.get('type', 'all')
        resolution = request.args.get('resolution', 'raw')
        limit = request.args.get('limit', 1000, type=int)
        
        # Даты по умолчанию
        if from_str:
            try:
                from_date = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            except ValueError:
                from_date = datetime.now() - timedelta(days=7)
        else:
            from_date = datetime.now() - timedelta(days=7)
        
        if to_str:
            try:
                to_date = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            except ValueError:
                to_date = datetime.now()
        else:
            to_date = datetime.now()
        
        # Получаем метрики из S3
        metrics_data = cloud.get_metrics(
            hostname=hostname,
            from_date=from_date,
            to_date=to_date,
            metric_type=metric_type,
            resolution=resolution,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'hostname': hostname,
                **metrics_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/events', methods=['GET'])
def get_events():
    """
    GET /api/metrics/events
    Получить события Windows за период.
    
    Query params:
        - computer_id: int (required)
        - from: datetime
        - to: datetime
        - type: windows_event|user_action|all
        - limit: int (по умолчанию 100)
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        if not computer_id:
            return jsonify({
                'success': False,
                'error': 'computer_id is required'
            }), 400
        
        hostname = mysql.get_computer_hostname(computer_id)
        if not hostname:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        event_type = request.args.get('type', 'all')
        limit = request.args.get('limit', 100, type=int)
        
        if from_str:
            try:
                from_date = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            except ValueError:
                from_date = datetime.now() - timedelta(days=7)
        else:
            from_date = datetime.now() - timedelta(days=7)
        
        if to_str:
            try:
                to_date = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            except ValueError:
                to_date = datetime.now()
        else:
            to_date = datetime.now()
        
        events_data = cloud.get_events(
            hostname=hostname,
            from_date=from_date,
            to_date=to_date,
            event_type=event_type,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'hostname': hostname,
                **events_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/summary', methods=['GET'])
def get_summary():
    """
    GET /api/metrics/summary
    Получить агрегированную статистику.
    
    Query params:
        - computer_id: int (required)
        - period: hour|day|week (по умолчанию day)
        - from: datetime
        - to: datetime
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        if not computer_id:
            return jsonify({
                'success': False,
                'error': 'computer_id is required'
            }), 400
        
        hostname = mysql.get_computer_hostname(computer_id)
        if not hostname:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        period = request.args.get('period', 'day')
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        
        from_date = None
        to_date = None
        
        if from_str:
            try:
                from_date = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        if to_str:
            try:
                to_date = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        summary_data = cloud.get_summary(
            hostname=hostname,
            from_date=from_date,
            to_date=to_date,
            period=period
        )
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                **summary_data
            }
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
    Получить аномалии (высокая нагрузка CPU/RAM, ошибки).
    
    Query params:
        - computer_id: int
        - from: datetime
        - to: datetime
        - cpu_threshold: float (по умолчанию 90)
        - ram_threshold: float (по умолчанию 90)
        - limit: int
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        hostname = None
        if computer_id:
            hostname = mysql.get_computer_hostname(computer_id)
            if not hostname:
                return jsonify({
                    'success': False,
                    'error': 'Computer not found'
                }), 404
        
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        cpu_threshold = request.args.get('cpu_threshold', 90, type=float)
        ram_threshold = request.args.get('ram_threshold', 90, type=float)
        limit = request.args.get('limit', 100, type=int)
        
        if from_str:
            try:
                from_date = datetime.fromisoformat(from_str.replace('Z', '+00:00'))
            except ValueError:
                from_date = datetime.now() - timedelta(days=7)
        else:
            from_date = datetime.now() - timedelta(days=7)
        
        if to_str:
            try:
                to_date = datetime.fromisoformat(to_str.replace('Z', '+00:00'))
            except ValueError:
                to_date = datetime.now()
        else:
            to_date = datetime.now()
        
        # Если hostname указан - получаем метрики конкретного компьютера
        if hostname:
            metrics_data = cloud.get_metrics(
                hostname=hostname,
                from_date=from_date,
                to_date=to_date,
                metric_type='all',
                resolution='raw',
                limit=5000
            )
            
            metrics = metrics_data.get('metrics', [])
            
            # Фильтруем аномалии
            anomalies = []
            for m in metrics:
                cpu = m.get('cpu_usage')
                ram = m.get('ram_usage')
                
                if (cpu is not None and cpu > cpu_threshold) or \
                   (ram is not None and ram > ram_threshold):
                    anomalies.append({
                        'timestamp': m.get('timestamp'),
                        'type': 'high_load',
                        'cpu_usage': cpu,
                        'ram_usage': ram,
                        'cpu_threshold': cpu_threshold,
                        'ram_threshold': ram_threshold
                    })
            
            # Сортируем по времени (новые первые)
            anomalies.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            if len(anomalies) > limit:
                anomalies = anomalies[:limit]
            
            return jsonify({
                'success': True,
                'data': {
                    'computer_id': computer_id,
                    'hostname': hostname,
                    'from': from_date.isoformat(),
                    'to': to_date.isoformat(),
                    'cpu_threshold': cpu_threshold,
                    'ram_threshold': ram_threshold,
                    'total_anomalies': len(anomalies),
                    'anomalies': anomalies
                }
            })
        else:
            # Получаем все компьютеры
            computers_result = mysql.get_computers(page=1, limit=100, status='all')
            computers = computers_result.get('computers', [])
            
            all_anomalies = []
            
            for comp in computers:
                comp_id = comp.get('computer_id')
                comp_hostname = comp.get('hostname')
                
                if not comp_hostname:
                    continue
                
                metrics_data = cloud.get_metrics(
                    hostname=comp_hostname,
                    from_date=from_date,
                    to_date=to_date,
                    metric_type='all',
                    resolution='raw',
                    limit=1000
                )
                
                metrics = metrics_data.get('metrics', [])
                
                for m in metrics:
                    cpu = m.get('cpu_usage')
                    ram = m.get('ram_usage')
                    
                    if (cpu is not None and cpu > cpu_threshold) or \
                       (ram is not None and ram > ram_threshold):
                        all_anomalies.append({
                            'computer_id': comp_id,
                            'hostname': comp_hostname,
                            'timestamp': m.get('timestamp'),
                            'type': 'high_load',
                            'cpu_usage': cpu,
                            'ram_usage': ram
                        })
            
            all_anomalies.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            if len(all_anomalies) > limit:
                all_anomalies = all_anomalies[:limit]
            
            return jsonify({
                'success': True,
                'data': {
                    'from': from_date.isoformat(),
                    'to': to_date.isoformat(),
                    'cpu_threshold': cpu_threshold,
                    'ram_threshold': ram_threshold,
                    'total_anomalies': len(all_anomalies),
                    'anomalies': all_anomalies
                }
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Дополнительные эндпоинты для железа, IP, ОС, статусов

@metrics_bp.route('/hardware', methods=['GET'])
def get_hardware():
    """
    GET /api/metrics/hardware
    Получить список конфигураций железа.
    
    Query params:
        - page: int
        - limit: int
        - unique: bool (только уникальные)
    """
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        unique = request.args.get('unique', 'false').lower() in ('true', '1', 'yes')
        
        if unique:
            configs = mysql.get_unique_hardware_configs()
            return jsonify({
                'success': True,
                'data': {
                    'configs': configs,
                    'total': len(configs)
                }
            })
        else:
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


@metrics_bp.route('/hardware/<int:config_id>', methods=['GET'])
def get_hardware_config(config_id):
    """
    GET /api/metrics/hardware/{id}
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


@metrics_bp.route('/ip-addresses', methods=['GET'])
def get_ip_addresses():
    """
    GET /api/metrics/ip-addresses
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


@metrics_bp.route('/ip-addresses/current', methods=['GET'])
def get_current_ips():
    """
    GET /api/metrics/ip-addresses/current
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


@metrics_bp.route('/operating-systems', methods=['GET'])
def get_operating_systems():
    """
    GET /api/metrics/operating-systems
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


@metrics_bp.route('/os-families', methods=['GET'])
def get_os_families():
    """
    GET /api/metrics/os-families
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


@metrics_bp.route('/statuses', methods=['GET'])
def get_statuses():
    """
    GET /api/metrics/statuses
    Получить список статусов.
    """
    try:
        statuses = mysql.get_statuses()
        
        return jsonify({
            'success': True,
            'data': statuses
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Эндпоинты для работы с сессиями

@metrics_bp.route('/sessions', methods=['GET'])
def get_sessions():
    """
    GET /api/metrics/sessions
    Получить список сессий за период.
    
    Query params:
        - computer_id: int (required) - ID компьютера
        - from: date (YYYY-MM-DD) - начало периода
        - to: date (YYYY-MM-DD) - конец периода
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        if not computer_id:
            return jsonify({
                'success': False,
                'error': 'computer_id is required'
            }), 400
        
        hostname = mysql.get_computer_hostname(computer_id)
        if not hostname:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        
        from_date = None
        to_date = None
        
        if from_str:
            try:
                from_date = datetime.strptime(from_str, '%Y-%m-%d').date()
            except ValueError:
                from_date = (datetime.now() - timedelta(days=7)).date()
        else:
            from_date = (datetime.now() - timedelta(days=7)).date()
        
        if to_str:
            try:
                to_date = datetime.strptime(to_str, '%Y-%m-%d').date()
            except ValueError:
                to_date = datetime.now().date()
        else:
            to_date = datetime.now().date()
        
        sessions_data = cloud.get_sessions(
            hostname=hostname,
            from_date=from_date,
            to_date=to_date
        )
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                'hostname': hostname,
                **sessions_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/sessions/<session_token>/metrics', methods=['GET'])
def get_session_metrics(session_token):
    """
    GET /api/metrics/sessions/{session_token}/metrics
    Получить метрики конкретной сессии.
    
    Query params:
        - computer_id: int (required) - ID компьютера
        - type: cpu|ram|disk|network|all (по умолчанию all)
        - limit: int (по умолчанию 1000)
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        if not computer_id:
            return jsonify({
                'success': False,
                'error': 'computer_id is required'
            }), 400
        
        hostname = mysql.get_computer_hostname(computer_id)
        if not hostname:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        metric_type = request.args.get('type', 'all')
        limit = request.args.get('limit', 1000, type=int)
        
        metrics_data = cloud.get_session_metrics(
            hostname=hostname,
            session_token=session_token,
            metric_type=metric_type,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                **metrics_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@metrics_bp.route('/sessions/<session_token>/events', methods=['GET'])
def get_session_events(session_token):
    """
    GET /api/metrics/sessions/{session_token}/events
    Получить события конкретной сессии.
    
    Query params:
        - computer_id: int (required) - ID компьютера
        - type: windows_event|user_action|all (по умолчанию all)
        - limit: int (по умолчанию 100)
    """
    try:
        computer_id = request.args.get('computer_id', type=int)
        
        if not computer_id:
            return jsonify({
                'success': False,
                'error': 'computer_id is required'
            }), 400
        
        hostname = mysql.get_computer_hostname(computer_id)
        if not hostname:
            return jsonify({
                'success': False,
                'error': 'Computer not found'
            }), 404
        
        event_type = request.args.get('type', 'all')
        limit = request.args.get('limit', 100, type=int)
        
        events_data = cloud.get_session_events(
            hostname=hostname,
            session_token=session_token,
            event_type=event_type,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'data': {
                'computer_id': computer_id,
                **events_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
