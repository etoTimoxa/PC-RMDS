"""
Computers routes - эндпоинты для работы с компьютерами
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import secrets
import hashlib

from services.mysql_service import MySQLService

computers_bp = Blueprint('computers', __name__)
mysql = MySQLService()


# ============================================
# ГРУППЫ КОМПЬЮТЕРОВ
# ============================================

@computers_bp.route('/groups', methods=['GET'])
def get_computer_groups():
    """Получить список всех групп компьютеров"""
    try:
        groups = mysql.fetch_all("""
            SELECT 
                cg.*,
                (SELECT COUNT(*) FROM computer WHERE group_id = cg.group_id) as computer_count
            FROM computer_group cg
            ORDER BY cg.group_name
        """)
        
        return jsonify({
            'success': True,
            'data': groups
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/groups', methods=['POST'])
def create_computer_group():
    """Создать новую группу компьютеров"""
    try:
        data = request.get_json()
        
        if not data or 'group_name' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует обязательное поле: group_name'
            }), 400
        
        group_id = mysql.execute("""
            INSERT INTO computer_group (group_name, description)
            VALUES (%s, %s)
        """, (
            data['group_name'],
            data.get('description')
        ))
        
        return jsonify({
            'success': True,
            'message': 'Группа создана',
            'data': {'group_id': group_id}
        }), 201
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/groups/<int:group_id>', methods=['PUT'])
def update_computer_group_by_id(group_id):
    """Обновить группу компьютеров"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        update_fields = []
        params = []
        
        if 'group_name' in data:
            update_fields.append("group_name = %s")
            params.append(data['group_name'])
        if 'description' in data:
            update_fields.append("description = %s")
            params.append(data['description'])
        
        if not update_fields:
            return jsonify({
                'success': False,
                'error': 'No valid fields to update'
            }), 400
        
        params.append(group_id)
        mysql.execute(f"""
            UPDATE computer_group SET {', '.join(update_fields)}
            WHERE group_id = %s
        """, params)
        
        return jsonify({
            'success': True,
            'message': 'Группа обновлена'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/groups/<int:group_id>', methods=['DELETE'])
def delete_computer_group(group_id):
    """Удалить группу компьютеров"""
    try:
        # Проверяем, есть ли компьютеры в группе
        computers_in_group = mysql.fetch_one(
            "SELECT COUNT(*) as count FROM computer WHERE group_id = %s",
            (group_id,)
        )
        
        if computers_in_group and computers_in_group['count'] > 0:
            # Отвязываем компьютеры от группы
            mysql.execute(
                "UPDATE computer SET group_id = NULL WHERE group_id = %s",
                (group_id,)
            )
        
        mysql.execute("DELETE FROM computer_group WHERE group_id = %s", (group_id,))
        
        return jsonify({
            'success': True,
            'message': 'Группа удалена'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/groups/<int:group_id>/computers', methods=['GET'])
def get_computers_by_group(group_id):
    """Получить компьютеры в группе"""
    try:
        computers = mysql.fetch_all("""
            SELECT 
                c.computer_id, c.hostname, c.mac_address, c.computer_type,
                c.is_online, c.last_online, c.description, c.inventory_number,
                u.login, u.full_name,
                (SELECT ip_address FROM ip_address WHERE computer_id = c.computer_id 
                 ORDER BY detected_at DESC LIMIT 1) as ip_address
            FROM computer c
            LEFT JOIN user u ON c.user_id = u.user_id
            WHERE c.group_id = %s
            ORDER BY c.hostname
        """, (group_id,))
        
        return jsonify({
            'success': True,
            'data': {
                'group_id': group_id,
                'computers': computers,
                'count': len(computers)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# КОМПЬЮТЕРЫ
# ============================================

@computers_bp.route('/register', methods=['POST'])
def register_computer():
    """
    POST /api/computers/register
    Регистрация компьютера для пользователя с полной информацией о железе
    """
    try:
        data = request.get_json()
        
        print(f"🔵 [СЕРВЕР] Получены данные регистрации:")
        print(f"   user_id: {data.get('user_id')}")
        print(f"   hostname: {data.get('hostname')}")
        print(f"   mac_address: {data.get('mac_address')}")
        
        required_fields = ['user_id', 'hostname', 'mac_address']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400
                
        user_id = data['user_id']
        hostname = data['hostname']
        mac_address = data['mac_address']
        force_rebind = data.get('force_rebind', False)
        ip_address = data.get('ip_address')
        group_id = data.get('group_id')
        description = data.get('description')
        inventory_number = data.get('inventory_number')
        
        # ============================================
        # 1. РАБОТА С ОПЕРАЦИОННОЙ СИСТЕМОЙ
        # ============================================
        os_name = data.get('os_name', 'Windows')
        os_version = data.get('os_version', '10')
        os_architecture = data.get('os_architecture', 'x64')
        
        family_id = 1
        if os_name.lower() == 'windows':
            family_id = 1
        elif os_name.lower() == 'linux':
            family_id = 2
        elif os_name.lower() == 'macos' or os_name.lower() == 'darwin':
            family_id = 3
        
        existing_os = mysql.fetch_one("""
            SELECT os_id FROM operating_system 
            WHERE os_name = %s AND os_version = %s
        """, (os_name, os_version))
        
        if existing_os:
            os_id = existing_os['os_id']
        else:
            os_id = mysql.execute("""
                INSERT INTO operating_system (os_name, os_version, os_architecture, family_id)
                VALUES (%s, %s, %s, %s)
            """, (os_name, os_version, os_architecture, family_id))
        
        # ============================================
        # 2. РАБОТА С КОНФИГУРАЦИЕЙ ЖЕЛЕЗА
        # ============================================
        cpu_model = data.get('cpu_model', 'Unknown')
        cpu_cores = data.get('cpu_cores')
        ram_total = data.get('ram_total', 0)
        storage_total = data.get('storage_total', 0)
        gpu_model = data.get('gpu_model')
        motherboard = data.get('motherboard')
        bios_version = data.get('bios_version')
        
        existing_config = None
        if cpu_model and cpu_model != 'Unknown':
            existing_config = mysql.fetch_one("""
                SELECT config_id FROM hardware_config 
                WHERE cpu_model = %s AND cpu_cores = %s AND ram_total = %s
            """, (cpu_model, cpu_cores, ram_total))
        
        if existing_config:
            hardware_config_id = existing_config['config_id']
        else:
            hardware_config_id = mysql.execute("""
                INSERT INTO hardware_config (
                    cpu_model, cpu_cores, ram_total, storage_total, 
                    gpu_model, motherboard, bios_version, detected_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """, (cpu_model, cpu_cores, ram_total, storage_total, 
                  gpu_model, motherboard, bios_version))
        
        # ============================================
        # 3. РАБОТА С КОМПЬЮТЕРОМ
        # ============================================
        existing_computer = mysql.fetch_one(
            "SELECT computer_id, user_id FROM computer WHERE mac_address = %s",
            (mac_address,)
        )
        
        already_bound = False
        other_user_id = None
        other_user_login = None
        
        if existing_computer:
            computer_id = existing_computer['computer_id']
            current_user_id = existing_computer['user_id']
            
            if current_user_id and current_user_id != user_id:
                already_bound = True
                other_user_id = current_user_id
                other_user = mysql.fetch_one("SELECT login FROM user WHERE user_id = %s", (current_user_id,))
                other_user_login = other_user['login'] if other_user else 'Unknown'
                
                if force_rebind:
                    mysql.execute("""
                        UPDATE computer 
                        SET user_id = %s, hostname = %s, os_id = %s, hardware_config_id = %s,
                            group_id = %s, description = %s, inventory_number = %s,
                            is_online = 1, last_online = NOW()
                        WHERE computer_id = %s
                    """, (user_id, hostname, os_id, hardware_config_id, 
                          group_id, description, inventory_number, computer_id))
                else:
                    mysql.execute("""
                        UPDATE computer 
                        SET hostname = %s, os_id = %s, hardware_config_id = %s,
                            group_id = %s, description = %s, inventory_number = %s,
                            is_online = 1, last_online = NOW()
                        WHERE computer_id = %s
                    """, (hostname, os_id, hardware_config_id, 
                          group_id, description, inventory_number, computer_id))
            else:
                mysql.execute("""
                    UPDATE computer 
                    SET hostname = %s, os_id = %s, hardware_config_id = %s,
                        group_id = %s, description = %s, inventory_number = %s,
                        is_online = 1, last_online = NOW()
                    WHERE computer_id = %s
                """, (hostname, os_id, hardware_config_id, 
                      group_id, description, inventory_number, computer_id))
        else:
            computer_id = mysql.execute("""
                INSERT INTO computer (
                    user_id, hostname, mac_address, os_id, hardware_config_id,
                    group_id, description, inventory_number,
                    computer_type, is_online, created_at, last_online
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'client', 1, NOW(), NOW())
            """, (user_id, hostname, mac_address, os_id, hardware_config_id,
                  group_id, description, inventory_number))
        
        # ============================================
        # 4. ДОБАВЛЯЕМ IP АДРЕС
        # ============================================
        if ip_address:
            existing_ip = mysql.fetch_one("""
                SELECT ip_id FROM ip_address 
                WHERE computer_id = %s AND ip_address = %s
                ORDER BY detected_at DESC LIMIT 1
            """, (computer_id, ip_address))
            
            if not existing_ip:
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
                'hostname': hostname,
                'mac_address': mac_address,
                'os_id': os_id,
                'hardware_config_id': hardware_config_id,
                'group_id': group_id,
                'is_online': 1,
                'is_new': existing_computer is None,
                'already_bound': already_bound,
                'other_user_id': other_user_id,
                'other_user_login': other_user_login
            }
        })
        
    except Exception as e:
        print(f"❌ [СЕРВЕР] Ошибка регистрации компьютера: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('', methods=['GET'])
def get_computers():
    """Получить список компьютеров"""
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        status = request.args.get('status', 'all')
        computer_type = request.args.get('type', 'all')
        search = request.args.get('search')
        user_id = request.args.get('user_id', type=int)
        group_id = request.args.get('group_id', type=int)
        
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                where_clauses = ["1=1"]
                params = []
                
                if status == 'online':
                    where_clauses.append("c.is_online = 1")
                elif status == 'offline':
                    where_clauses.append("c.is_online = 0")
                
                if computer_type != 'all':
                    where_clauses.append("c.computer_type = %s")
                    params.append(computer_type)
                
                if search:
                    where_clauses.append("(c.hostname LIKE %s OR c.mac_address LIKE %s OR c.inventory_number LIKE %s OR cg.group_name LIKE %s)")
                    params.append(f"%{search}%")
                    params.append(f"%{search}%")
                    params.append(f"%{search}%")
                    params.append(f"%{search}%")
                
                if user_id:
                    where_clauses.append("c.user_id = %s")
                    params.append(user_id)
                
                if group_id:
                    where_clauses.append("c.group_id = %s")
                    params.append(group_id)
                
                where_sql = " AND ".join(where_clauses)
                offset = (page - 1) * limit
                
                cursor.execute(f"""
                    SELECT COUNT(*) as total 
                    FROM computer c
                    LEFT JOIN computer_group cg ON c.group_id = cg.group_id
                    WHERE {where_sql}
                """, params)
                total = cursor.fetchone()['total']
                
                cursor.execute(f"""
                    SELECT 
                        c.computer_id, c.hostname, c.mac_address, c.computer_type,
                        c.is_online, c.last_online, c.created_at, c.description,
                        c.inventory_number,
                        cg.group_id, cg.group_name,
                        u.user_id, u.login, u.full_name,
                        os.os_id, os.os_name, os.os_version,
                        hc.config_id, hc.cpu_model, hc.cpu_cores, hc.ram_total, hc.storage_total,
                        (SELECT ip_address FROM ip_address WHERE computer_id = c.computer_id 
                         ORDER BY detected_at DESC LIMIT 1) as ip_address
                    FROM computer c
                    LEFT JOIN user u ON c.user_id = u.user_id
                    LEFT JOIN computer_group cg ON c.group_id = cg.group_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    LEFT JOIN hardware_config hc ON c.hardware_config_id = hc.config_id
                    WHERE {where_sql}
                    ORDER BY c.last_online DESC
                    LIMIT %s OFFSET %s
                """, params + [limit, offset])
                
                computers = cursor.fetchall()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'computers': computers,
                        'total': total,
                        'page': page,
                        'limit': limit,
                        'pages': (total + limit - 1) // limit if limit > 0 else 0
                    }
                })
        
    except Exception as e:
        print(f"❌ Ошибка получения компьютеров: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>', methods=['GET'])
def get_computer_by_id(computer_id):
    """Получить компьютер по ID"""
    try:
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        c.*,
                        u.login, u.full_name, u.role_id,
                        cg.group_id, cg.group_name,
                        os.os_name, os.os_version, os.os_architecture,
                        hc.cpu_model, hc.cpu_cores, hc.ram_total, hc.storage_total,
                        hc.gpu_model, hc.motherboard, hc.bios_version,
                        (SELECT ip_address FROM ip_address WHERE computer_id = c.computer_id 
                         ORDER BY detected_at DESC LIMIT 1) as current_ip
                    FROM computer c
                    LEFT JOIN user u ON c.user_id = u.user_id
                    LEFT JOIN computer_group cg ON c.group_id = cg.group_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    LEFT JOIN hardware_config hc ON c.hardware_config_id = hc.config_id
                    WHERE c.computer_id = %s
                """, (computer_id,))
                
                computer = cursor.fetchone()
                
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
        print(f"❌ Ошибка получения компьютера: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>', methods=['PUT'])
def update_computer_by_id(computer_id):
    """Обновить данные компьютера (группа, инвентарный номер, описание и т.д.)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        allowed_fields = ['hostname', 'description', 'computer_type', 'user_id', 
                          'group_id', 'inventory_number']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return jsonify({
                'success': False,
                'error': 'No valid fields to update'
            }), 400
        
        # Если меняется user_id, проверяем что пользователь существует
        if 'user_id' in update_fields:
            new_user_id = update_fields['user_id']
            user_exists = mysql.fetch_one("SELECT user_id FROM user WHERE user_id = %s", (new_user_id,))
            if not user_exists:
                return jsonify({
                    'success': False,
                    'error': f'Пользователь с ID {new_user_id} не найден'
                }), 404
        
        # Если меняется group_id, проверяем что группа существует (если не NULL)
        if 'group_id' in update_fields and update_fields['group_id']:
            group_exists = mysql.fetch_one("SELECT group_id FROM computer_group WHERE group_id = %s", (update_fields['group_id'],))
            if not group_exists:
                return jsonify({
                    'success': False,
                    'error': f'Группа с ID {update_fields["group_id"]} не найдена'
                }), 404
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE computer SET {set_clause} WHERE computer_id = %s"
        
        mysql.execute(sql, list(update_fields.values()) + [computer_id])
        
        updated_computer = mysql.fetch_one("SELECT * FROM computer WHERE computer_id = %s", (computer_id,))
        
        return jsonify({
            'success': True,
            'message': 'Computer updated successfully',
            'data': updated_computer
        })
        
    except Exception as e:
        print(f"❌ Ошибка обновления компьютера: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/sessions', methods=['GET'])
def get_computer_sessions_by_id(computer_id):
    """Получить сессии компьютера"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        s.session_id, s.session_token, s.start_time, s.last_activity,
                        s.end_time, s.status_id, s.json_sent_count, s.error_count,
                        st.status_name
                    FROM session s
                    LEFT JOIN status st ON s.status_id = st.status_id
                    WHERE s.computer_id = %s
                    ORDER BY s.start_time DESC
                    LIMIT %s
                """, (computer_id, limit))
                
                sessions = cursor.fetchall()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'computer_id': computer_id,
                        'sessions': sessions
                    }
                })
        
    except Exception as e:
        print(f"❌ Ошибка получения сессий: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/sessions/<int:session_id>/close', methods=['POST'])
def close_computer_session(computer_id, session_id):
    """Принудительно закрыть сессию компьютера"""
    try:
        session = mysql.fetch_one("""
            SELECT session_id, status_id, computer_id 
            FROM session 
            WHERE session_id = %s AND computer_id = %s
        """, (session_id, computer_id))
        
        if not session:
            return jsonify({
                'success': False,
                'error': 'Сессия не найдена'
            }), 404
        
        if session['status_id'] == 2:
            return jsonify({
                'success': False,
                'error': 'Сессия уже закрыта'
            }), 400
        
        mysql.execute("""
            UPDATE session 
            SET status_id = 2, end_time = NOW()
            WHERE session_id = %s
        """, (session_id,))
        
        active_sessions = mysql.fetch_one("""
            SELECT COUNT(*) as count FROM session 
            WHERE computer_id = %s AND status_id = 1
        """, (computer_id,))
        
        if active_sessions and active_sessions['count'] == 0:
            mysql.execute("""
                UPDATE computer SET is_online = 0, last_online = NOW()
                WHERE computer_id = %s
            """, (computer_id,))
        
        return jsonify({
            'success': True,
            'message': f'Сессия {session_id} успешно закрыта'
        })
        
    except Exception as e:
        print(f"❌ Ошибка закрытия сессии: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/ip', methods=['POST'])
def update_computer_ip(computer_id):
    """Обновить IP адрес компьютера (только если он изменился)"""
    try:
        data = request.get_json()
        
        if not data or 'ip_address' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует обязательное поле: ip_address'
            }), 400
        
        ip_address = data['ip_address']
        
        existing_ip = mysql.fetch_one("""
            SELECT ip_id, detected_at FROM ip_address 
            WHERE computer_id = %s AND ip_address = %s
            ORDER BY detected_at DESC LIMIT 1
        """, (computer_id, ip_address))
        
        if existing_ip:
            mysql.execute("""
                UPDATE ip_address SET detected_at = NOW()
                WHERE ip_id = %s
            """, (existing_ip['ip_id'],))
        else:
            mysql.execute("""
                INSERT INTO ip_address (computer_id, ip_address, detected_at)
                VALUES (%s, %s, NOW())
            """, (computer_id, ip_address))
        
        return jsonify({
            'success': True,
            'message': 'IP адрес обновлен'
        })
        
    except Exception as e:
        print(f"❌ Ошибка обновления IP адреса: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/status', methods=['PUT'])
def update_computer_status(computer_id):
    """Обновить статус компьютера"""
    try:
        data = request.get_json()
        
        if not data or 'is_online' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует обязательное поле is_online'
            }), 400
            
        is_online = bool(data['is_online'])
        
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
        print(f"❌ Ошибка обновления статуса: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>/ip-addresses', methods=['GET'])
def get_computer_ip_addresses(computer_id):
    """Получить IP адреса компьютера"""
    try:
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT ip_id, ip_address, subnet_mask, gateway, detected_at
                    FROM ip_address
                    WHERE computer_id = %s
                    ORDER BY detected_at DESC
                """, (computer_id,))
                
                addresses = cursor.fetchall()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'computer_id': computer_id,
                        'ip_addresses': addresses
                    }
                })
        
    except Exception as e:
        print(f"❌ Ошибка получения IP адресов: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/<int:computer_id>', methods=['DELETE'])
def delete_computer(computer_id):
    """Удалить компьютер"""
    try:
        mysql.execute("DELETE FROM computer WHERE computer_id = %s", (computer_id,))
        
        return jsonify({
            'success': True,
            'message': 'Computer deleted successfully'
        })
        
    except Exception as e:
        print(f"❌ Ошибка удаления компьютера: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# УПРАВЛЕНИЕ ПАРОЛЯМИ
# ============================================

@computers_bp.route('/user/<int:user_id>/reset-password', methods=['POST'])
def request_password_reset(user_id):
    """Запрос на сброс пароля (создание токена)"""
    try:
        user = mysql.fetch_one("SELECT user_id, login FROM user WHERE user_id = %s", (user_id,))
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Пользователь не найден'
            }), 404
        
        reset_token = secrets.token_urlsafe(32)
        reset_expires = datetime.now() + timedelta(hours=24)
        
        mysql.execute("""
            UPDATE user 
            SET reset_password_token = %s, reset_password_expires = %s
            WHERE user_id = %s
        """, (reset_token, reset_expires, user_id))
        
        return jsonify({
            'success': True,
            'message': 'Токен для сброса пароля создан',
            'data': {
                'reset_token': reset_token,
                'expires_at': reset_expires.isoformat()
            }
        })
        
    except Exception as e:
        print(f"❌ Ошибка создания токена сброса: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/user/reset-password', methods=['POST'])
def reset_password():
    """Сброс пароля по токену"""
    try:
        data = request.get_json()
        
        if not data or 'reset_token' not in data or 'new_password' not in data:
            return jsonify({
                'success': False,
                'error': 'Требуется reset_token и new_password'
            }), 400
        
        reset_token = data['reset_token']
        new_password = data['new_password']
        
        user = mysql.fetch_one("""
            SELECT user_id, reset_password_token, reset_password_expires 
            FROM user 
            WHERE reset_password_token = %s AND reset_password_expires > NOW()
        """, (reset_token,))
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Недействительный или просроченный токен'
            }), 400
        
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        
        mysql.execute("""
            UPDATE user 
            SET password_hash = %s, reset_password_token = NULL, reset_password_expires = NULL
            WHERE user_id = %s
        """, (password_hash, user['user_id']))
        
        return jsonify({
            'success': True,
            'message': 'Пароль успешно изменен'
        })
        
    except Exception as e:
        print(f"❌ Ошибка сброса пароля: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@computers_bp.route('/user/<int:user_id>/change-password', methods=['POST'])
def change_password(user_id):
    """Изменение пароля (требуется старый пароль)"""
    try:
        data = request.get_json()
        
        if not data or 'old_password' not in data or 'new_password' not in data:
            return jsonify({
                'success': False,
                'error': 'Требуется old_password и new_password'
            }), 400
        
        user = mysql.fetch_one(
            "SELECT user_id, password_hash FROM user WHERE user_id = %s",
            (user_id,)
        )
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Пользователь не найден'
            }), 404
        
        old_hash = hashlib.sha256(data['old_password'].encode()).hexdigest()
        if old_hash != user['password_hash']:
            return jsonify({
                'success': False,
                'error': 'Неверный старый пароль'
            }), 401
        
        new_hash = hashlib.sha256(data['new_password'].encode()).hexdigest()
        mysql.execute("UPDATE user SET password_hash = %s WHERE user_id = %s", (new_hash, user_id))
        
        return jsonify({
            'success': True,
            'message': 'Пароль успешно изменен'
        })
        
    except Exception as e:
        print(f"❌ Ошибка изменения пароля: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500