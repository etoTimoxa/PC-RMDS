"""
MySQL Service - работа с базой данных
"""
import pymysql
import pymysql.cursors
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from ..config import DB_CONFIG, PAGINATION


class MySQLService:
    """Сервис для работы с MySQL базой данных"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config = DB_CONFIG.copy()
        self._config['cursorclass'] = pymysql.cursors.DictCursor
    
    @contextmanager
    def get_connection(self):
        """Получить соединение с базой данных"""
        connection = pymysql.connect(**self._config)
        try:
            yield connection
        finally:
            connection.close()
    
    # =========================================================================
    # КОМПЬЮТЕРЫ
    # =========================================================================
    
    def get_computers(
        self,
        page: int = 1,
        limit: int = None,
        status: str = 'all',
        computer_type: str = 'all',
        search: str = None,
        user_id: int = None,
        os_id: int = None
    ) -> Dict:
        """Получить список компьютеров с пагинацией"""
        if limit is None:
            limit = PAGINATION['default_limit']
        limit = min(limit, PAGINATION['max_limit'])
        offset = (page - 1) * limit
        
        where_clauses = []
        params = []
        
        if status == 'online':
            where_clauses.append("c.is_online = 1")
        elif status == 'offline':
            where_clauses.append("c.is_online = 0")
        
        if computer_type != 'all':
            where_clauses.append("c.computer_type = %s")
            params.append(computer_type)
        
        if search:
            where_clauses.append("(c.hostname LIKE %s OR c.mac_address LIKE %s)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        
        if user_id:
            where_clauses.append("c.user_id = %s")
            params.append(user_id)
        
        if os_id:
            where_clauses.append("c.os_id = %s")
            params.append(os_id)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Получаем общее количество
                count_sql = f"SELECT COUNT(*) as total FROM computer c WHERE {where_sql}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()['total']
                
                # Получаем компьютеры с джоинами
                sql = f"""
                    SELECT 
                        c.computer_id,
                        c.hostname,
                        c.mac_address,
                        c.computer_type,
                        c.is_online,
                        c.last_online,
                        c.description,
                        c.created_at,
                        u.user_id,
                        u.login,
                        u.full_name,
                        os.os_id,
                        os.os_name,
                        os.os_version,
                        os.os_architecture,
                        hc.config_id,
                        hc.cpu_model,
                        hc.cpu_cores,
                        hc.ram_total,
                        hc.storage_total,
                        hc.gpu_model,
                        (SELECT ip_address FROM ip_address WHERE computer_id = c.computer_id ORDER BY detected_at DESC LIMIT 1) as ip_address,
                        (SELECT session_id FROM session WHERE computer_id = c.computer_id AND status_id = 1 LIMIT 1) as active_session_id
                    FROM computer c
                    LEFT JOIN user u ON c.user_id = u.user_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    LEFT JOIN hardware_config hc ON c.hardware_config_id = hc.config_id
                    WHERE {where_sql}
                    ORDER BY c.last_online DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, params + [limit, offset])
                computers = cursor.fetchall()
                
                return {
                    'computers': computers,
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'pages': (total + limit - 1) // limit if limit > 0 else 0
                }
    
    def get_computer_by_id(self, computer_id: int) -> Optional[Dict]:
        """Получить компьютер по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        c.*,
                        u.user_id,
                        u.login,
                        u.full_name,
                        u.role_id,
                        os.*,
                        hc.*,
                        (SELECT ip_address FROM ip_address WHERE computer_id = c.computer_id ORDER BY detected_at DESC LIMIT 1) as current_ip
                    FROM computer c
                    LEFT JOIN user u ON c.user_id = u.user_id
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    LEFT JOIN hardware_config hc ON c.hardware_config_id = hc.config_id
                    WHERE c.computer_id = %s
                """
                cursor.execute(sql, (computer_id,))
                return cursor.fetchone()
    
    def get_computer_hostname(self, computer_id: int) -> Optional[str]:
        """Получить hostname компьютера по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT hostname FROM computer WHERE computer_id = %s", (computer_id,))
                result = cursor.fetchone()
                return result['hostname'] if result else None
    
    def get_computer_sessions(self, computer_id: int, limit: int = 20) -> List[Dict]:
        """Получить историю сессий компьютера"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        s.session_id,
                        s.session_token,
                        s.start_time,
                        s.last_activity,
                        s.end_time,
                        s.json_sent_count,
                        s.error_count,
                        st.status_name,
                        st.status_id
                    FROM session s
                    LEFT JOIN status st ON s.status_id = st.status_id
                    WHERE s.computer_id = %s
                    ORDER BY s.start_time DESC
                    LIMIT %s
                """
                cursor.execute(sql, (computer_id, limit))
                return cursor.fetchall()
    
    def get_computer_ip_history(self, computer_id: int) -> List[Dict]:
        """Получить историю IP адресов компьютера"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM ip_address 
                    WHERE computer_id = %s 
                    ORDER BY detected_at DESC
                """, (computer_id,))
                return cursor.fetchall()
    
    def update_computer(self, computer_id: int, data: Dict) -> bool:
        """Обновить данные компьютера"""
        allowed_fields = ['hostname', 'description', 'computer_type']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE computer SET {set_clause} WHERE computer_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [computer_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_computer(self, computer_id: int) -> bool:
        """Удалить компьютер"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Удаляем связанные записи
                cursor.execute("DELETE FROM session WHERE computer_id = %s", (computer_id,))
                cursor.execute("DELETE FROM ip_address WHERE computer_id = %s", (computer_id,))
                cursor.execute("DELETE FROM computer WHERE computer_id = %s", (computer_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # ПОЛЬЗОВАТЕЛИ
    # =========================================================================
    
    def get_users(
        self,
        page: int = 1,
        limit: int = None,
        role_id: int = None,
        search: str = None,
        is_active: bool = None
    ) -> Dict:
        """Получить список пользователей"""
        if limit is None:
            limit = PAGINATION['default_limit']
        limit = min(limit, PAGINATION['max_limit'])
        offset = (page - 1) * limit
        
        where_clauses = []
        params = []
        
        if role_id:
            where_clauses.append("u.role_id = %s")
            params.append(role_id)
        
        if search:
            where_clauses.append("(u.login LIKE %s OR u.full_name LIKE %s)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        
        if is_active is not None:
            where_clauses.append("u.is_active = %s")
            params.append(1 if is_active else 0)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                count_sql = f"SELECT COUNT(*) as total FROM user u WHERE {where_sql}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()['total']
                
                sql = f"""
                    SELECT 
                        u.user_id,
                        u.login,
                        u.full_name,
                        u.role_id,
                        u.last_login,
                        u.is_active,
                        u.created_at,
                        r.role_name,
                        r.description as role_description,
                        (SELECT COUNT(*) FROM computer WHERE user_id = u.user_id) as computer_count
                    FROM user u
                    LEFT JOIN role r ON u.role_id = r.role_id
                    WHERE {where_sql}
                    ORDER BY u.last_login DESC NULLS LAST
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, params + [limit, offset])
                users = cursor.fetchall()
                
                return {
                    'users': users,
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'pages': (total + limit - 1) // limit if limit > 0 else 0
                }
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        u.*,
                        r.role_name,
                        r.description as role_description
                    FROM user u
                    LEFT JOIN role r ON u.role_id = r.role_id
                    WHERE u.user_id = %s
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchone()
    
    def get_user_computers(self, user_id: int) -> List[Dict]:
        """Получить компьютеры пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        c.*,
                        os.os_name,
                        os.os_version,
                        (SELECT ip_address FROM ip_address WHERE computer_id = c.computer_id ORDER BY detected_at DESC LIMIT 1) as ip_address
                    FROM computer c
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    WHERE c.user_id = %s
                    ORDER BY c.last_online DESC
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchall()
    
    def create_user(self, data: Dict) -> int:
        """Создать пользователя"""
        import hashlib
        
        required = ['login', 'password', 'role_id']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        password_hash = hashlib.sha256(data['password'].encode()).hexdigest()
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO user (login, password_hash, full_name, role_id, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, (
                    data['login'],
                    password_hash,
                    data.get('full_name', data['login']),
                    data['role_id'],
                    data.get('is_active', 1)
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_user(self, user_id: int, data: Dict) -> bool:
        """Обновить пользователя"""
        import hashlib
        
        allowed_fields = ['login', 'full_name', 'role_id', 'is_active']
        update_fields = {}
        
        for k, v in data.items():
            if k in allowed_fields:
                update_fields[k] = v
            elif k == 'password':
                update_fields['password_hash'] = hashlib.sha256(v.encode()).hexdigest()
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE user SET {set_clause} WHERE user_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [user_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_user(self, user_id: int) -> bool:
        """Удалить пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Отвязываем компьютеры
                cursor.execute("UPDATE computer SET user_id = NULL WHERE user_id = %s", (user_id,))
                # Удаляем пользователя
                cursor.execute("DELETE FROM user WHERE user_id = %s", (user_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # РОЛИ
    # =========================================================================
    
    def get_roles(self) -> List[Dict]:
        """Получить все роли"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        r.*,
                        (SELECT COUNT(*) FROM user WHERE role_id = r.role_id) as user_count
                    FROM role r
                    ORDER BY r.role_id
                """)
                return cursor.fetchall()
    
    def get_role_by_id(self, role_id: int) -> Optional[Dict]:
        """Получить роль по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM role WHERE role_id = %s", (role_id,))
                return cursor.fetchone()
    
    def get_role_users(self, role_id: int) -> List[Dict]:
        """Получить пользователей с этой ролью"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, login, full_name, last_login, is_active
                    FROM user WHERE role_id = %s
                    ORDER BY last_login DESC
                """, (role_id,))
                return cursor.fetchall()
    
    def create_role(self, data: Dict) -> int:
        """Создать роль"""
        required = ['role_name']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO role (role_name, description, created_at)
                    VALUES (%s, %s, NOW())
                """
                cursor.execute(sql, (
                    data['role_name'],
                    data.get('description', '')
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_role(self, role_id: int, data: Dict) -> bool:
        """Обновить роль"""
        allowed_fields = ['role_name', 'description']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE role SET {set_clause} WHERE role_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [role_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_role(self, role_id: int) -> bool:
        """Удалить роль"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Проверяем есть ли пользователи с этой ролью
                cursor.execute("SELECT COUNT(*) as count FROM user WHERE role_id = %s", (role_id,))
                if cursor.fetchone()['count'] > 0:
                    raise ValueError("Cannot delete role with assigned users")
                
                cursor.execute("DELETE FROM role WHERE role_id = %s", (role_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # СЕССИИ
    # =========================================================================
    
    def get_sessions(
        self,
        page: int = 1,
        limit: int = None,
        computer_id: int = None,
        status_id: int = None,
        from_date: datetime = None,
        to_date: datetime = None
    ) -> Dict:
        """Получить список сессий"""
        if limit is None:
            limit = PAGINATION['default_limit']
        limit = min(limit, PAGINATION['max_limit'])
        offset = (page - 1) * limit
        
        where_clauses = []
        params = []
        
        if computer_id:
            where_clauses.append("s.computer_id = %s")
            params.append(computer_id)
        
        if status_id:
            where_clauses.append("s.status_id = %s")
            params.append(status_id)
        
        if from_date:
            where_clauses.append("s.start_time >= %s")
            params.append(from_date)
        
        if to_date:
            where_clauses.append("s.start_time <= %s")
            params.append(to_date)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                count_sql = f"SELECT COUNT(*) as total FROM session s WHERE {where_sql}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()['total']
                
                sql = f"""
                    SELECT 
                        s.*,
                        c.hostname,
                        c.computer_type,
                        st.status_name,
                        st.status_type
                    FROM session s
                    LEFT JOIN computer c ON s.computer_id = c.computer_id
                    LEFT JOIN status st ON s.status_id = st.status_id
                    WHERE {where_sql}
                    ORDER BY s.start_time DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, params + [limit, offset])
                sessions = cursor.fetchall()
                
                return {
                    'sessions': sessions,
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'pages': (total + limit - 1) // limit if limit > 0 else 0
                }
    
    def get_session_by_id(self, session_id: int) -> Optional[Dict]:
        """Получить сессию по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        s.*,
                        c.hostname,
                        c.mac_address,
                        c.computer_type,
                        st.status_name
                    FROM session s
                    LEFT JOIN computer c ON s.computer_id = c.computer_id
                    LEFT JOIN status st ON s.status_id = st.status_id
                    WHERE s.session_id = %s
                """
                cursor.execute(sql, (session_id,))
                return cursor.fetchone()
    
    def get_active_sessions(self) -> List[Dict]:
        """Получить активные сессии"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        s.*,
                        c.hostname,
                        c.computer_type,
                        u.login,
                        u.full_name
                    FROM session s
                    LEFT JOIN computer c ON s.computer_id = c.computer_id
                    LEFT JOIN user u ON c.user_id = u.user_id
                    WHERE s.status_id = 1
                    ORDER BY s.start_time DESC
                """
                cursor.execute(sql)
                return cursor.fetchall()
    
    def update_session(self, session_id: int, data: Dict) -> bool:
        """Обновить сессию"""
        allowed_fields = ['status_id', 'end_time', 'last_activity', 'json_sent_count', 'error_count']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE session SET {set_clause} WHERE session_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [session_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_session(self, session_id: int) -> bool:
        """Удалить сессию"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM session WHERE session_id = %s", (session_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # ЖЕЛЕЗО
    # =========================================================================
    
    def get_hardware_configs(
        self,
        page: int = 1,
        limit: int = None
    ) -> Dict:
        """Получить список конфигураций железа"""
        if limit is None:
            limit = PAGINATION['default_limit']
        limit = min(limit, PAGINATION['max_limit'])
        offset = (page - 1) * limit
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as total FROM hardware_config")
                total = cursor.fetchone()['total']
                
                sql = """
                    SELECT 
                        hc.*,
                        (SELECT COUNT(*) FROM computer WHERE hardware_config_id = hc.config_id) as computer_count
                    FROM hardware_config hc
                    ORDER BY hc.detected_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (limit, offset))
                configs = cursor.fetchall()
                
                return {
                    'configs': configs,
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'pages': (total + limit - 1) // limit if limit > 0 else 0
                }
    
    def get_hardware_config_by_id(self, config_id: int) -> Optional[Dict]:
        """Получить конфигурацию железа по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM hardware_config WHERE config_id = %s", (config_id,))
                return cursor.fetchone()
    
    def get_unique_hardware_configs(self) -> List[Dict]:
        """Получить уникальные конфигурации железа"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT DISTINCT
                        hc.cpu_model,
                        hc.cpu_cores,
                        hc.ram_total,
                        hc.storage_total,
                        hc.gpu_model,
                        COUNT(*) as computer_count
                    FROM hardware_config hc
                    GROUP BY 
                        hc.cpu_model,
                        hc.cpu_cores,
                        hc.ram_total,
                        hc.storage_total,
                        hc.gpu_model
                    ORDER BY computer_count DESC
                """
                cursor.execute(sql)
                return cursor.fetchall()
    
    def create_hardware_config(self, data: Dict) -> int:
        """Создать конфигурацию железа"""
        required = ['cpu_model']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO hardware_config 
                    (cpu_model, cpu_cores, ram_total, storage_total, gpu_model, motherboard, bios_version, detected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, (
                    data['cpu_model'],
                    data.get('cpu_cores'),
                    data.get('ram_total'),
                    data.get('storage_total'),
                    data.get('gpu_model'),
                    data.get('motherboard'),
                    data.get('bios_version')
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_hardware_config(self, config_id: int, data: Dict) -> bool:
        """Обновить конфигурацию железа"""
        allowed_fields = ['cpu_model', 'cpu_cores', 'ram_total', 'storage_total', 'gpu_model', 'motherboard', 'bios_version']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE hardware_config SET {set_clause}, updated_at = NOW() WHERE config_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [config_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_hardware_config(self, config_id: int) -> bool:
        """Удалить конфигурацию железа"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Проверяем связанные компьютеры
                cursor.execute("SELECT COUNT(*) as count FROM computer WHERE hardware_config_id = %s", (config_id,))
                if cursor.fetchone()['count'] > 0:
                    # Отвязываем компьютеры
                    cursor.execute("UPDATE computer SET hardware_config_id = NULL WHERE hardware_config_id = %s", (config_id,))
                
                cursor.execute("DELETE FROM hardware_config WHERE config_id = %s", (config_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # IP АДРЕСА
    # =========================================================================
    
    def get_ip_history(
        self,
        page: int = 1,
        limit: int = None,
        computer_id: int = None
    ) -> Dict:
        """Получить историю IP адресов"""
        if limit is None:
            limit = PAGINATION['default_limit']
        limit = min(limit, PAGINATION['max_limit'])
        offset = (page - 1) * limit
        
        where_sql = "1=1"
        params = []
        
        if computer_id:
            where_sql = "ip.computer_id = %s"
            params.append(computer_id)
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                count_sql = f"SELECT COUNT(*) as total FROM ip_address ip WHERE {where_sql}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()['total']
                
                sql = f"""
                    SELECT 
                        ip.*,
                        c.hostname
                    FROM ip_address ip
                    LEFT JOIN computer c ON ip.computer_id = c.computer_id
                    WHERE {where_sql}
                    ORDER BY ip.detected_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, params + [limit, offset])
                addresses = cursor.fetchall()
                
                return {
                    'addresses': addresses,
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'pages': (total + limit - 1) // limit if limit > 0 else 0
                }
    
    def get_current_ips(self) -> List[Dict]:
        """Получить текущие IP всех компьютеров"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        c.computer_id,
                        c.hostname,
                        c.is_online,
                        ip.ip_address,
                        ip.subnet_mask,
                        ip.gateway,
                        ip.detected_at
                    FROM computer c
                    INNER JOIN (
                        SELECT ip1.*
                        FROM ip_address ip1
                        INNER JOIN (
                            SELECT computer_id, MAX(detected_at) as max_detected
                            FROM ip_address
                            GROUP BY computer_id
                        ) latest ON ip1.computer_id = latest.computer_id 
                                 AND ip1.detected_at = latest.max_detected
                    ) ip ON c.computer_id = ip.computer_id
                    ORDER BY c.hostname
                """
                cursor.execute(sql)
                return cursor.fetchall()
    
    def create_ip_address(self, data: Dict) -> int:
        """Создать IP адрес"""
        required = ['computer_id', 'ip_address']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO ip_address 
                    (computer_id, ip_address, subnet_mask, gateway, detected_at)
                    VALUES (%s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, (
                    data['computer_id'],
                    data['ip_address'],
                    data.get('subnet_mask'),
                    data.get('gateway')
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_ip_address(self, ip_id: int, data: Dict) -> bool:
        """Обновить IP адрес"""
        allowed_fields = ['ip_address', 'subnet_mask', 'gateway']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE ip_address SET {set_clause} WHERE ip_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [ip_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_ip_address(self, ip_id: int) -> bool:
        """Удалить IP адрес"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM ip_address WHERE ip_id = %s", (ip_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # ОПЕРАЦИОННЫЕ СИСТЕМЫ
    # =========================================================================
    
    def get_operating_systems(self) -> List[Dict]:
        """Получить все ОС"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        os.*,
                        of.family_name,
                        of.description as family_description,
                        (SELECT COUNT(*) FROM computer WHERE os_id = os.os_id) as computer_count
                    FROM operating_system os
                    LEFT JOIN os_family of ON os.family_id = of.family_id
                    ORDER BY of.family_name, os.os_name, os.os_version
                """
                cursor.execute(sql)
                return cursor.fetchall()
    
    def get_os_families(self) -> List[Dict]:
        """Получить семейства ОС"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        of.*,
                        (SELECT COUNT(*) FROM operating_system WHERE family_id = of.family_id) as os_count,
                        (SELECT COUNT(*) FROM computer c 
                         INNER JOIN operating_system os ON c.os_id = os.os_id 
                         WHERE os.family_id = of.family_id) as computer_count
                    FROM os_family of
                    ORDER BY of.family_name
                """
                cursor.execute(sql)
                return cursor.fetchall()
    
    # =========================================================================
    # СТАТУСЫ
    # =========================================================================
    
    def get_statuses(self) -> List[Dict]:
        """Получить все статусы"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM status ORDER BY status_id")
                return cursor.fetchall()
    
    def create_operating_system(self, data: Dict) -> int:
        """Создать ОС"""
        required = ['os_name', 'os_version', 'family_id']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO operating_system 
                    (os_name, os_version, os_build, os_architecture, family_id)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    data['os_name'],
                    data['os_version'],
                    data.get('os_build'),
                    data.get('os_architecture', 'x64'),
                    data['family_id']
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_operating_system(self, os_id: int, data: Dict) -> bool:
        """Обновить ОС"""
        allowed_fields = ['os_name', 'os_version', 'os_build', 'os_architecture', 'family_id']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE operating_system SET {set_clause} WHERE os_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [os_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_operating_system(self, os_id: int) -> bool:
        """Удалить ОС"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Проверяем связанные компьютеры
                cursor.execute("SELECT COUNT(*) as count FROM computer WHERE os_id = %s", (os_id,))
                if cursor.fetchone()['count'] > 0:
                    raise ValueError("Cannot delete OS with assigned computers")
                
                cursor.execute("DELETE FROM operating_system WHERE os_id = %s", (os_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    def create_os_family(self, data: Dict) -> int:
        """Создать семейство ОС"""
        required = ['family_name']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO os_family (family_name, description)
                    VALUES (%s, %s)
                """
                cursor.execute(sql, (
                    data['family_name'],
                    data.get('description', '')
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_os_family(self, family_id: int, data: Dict) -> bool:
        """Обновить семейство ОС"""
        allowed_fields = ['family_name', 'description']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE os_family SET {set_clause} WHERE family_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [family_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_os_family(self, family_id: int) -> bool:
        """Удалить семейство ОС"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Проверяем связанные ОС
                cursor.execute("SELECT COUNT(*) as count FROM operating_system WHERE family_id = %s", (family_id,))
                if cursor.fetchone()['count'] > 0:
                    raise ValueError("Cannot delete OS family with assigned operating systems")
                
                cursor.execute("DELETE FROM os_family WHERE family_id = %s", (family_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    def create_status(self, data: Dict) -> int:
        """Создать статус"""
        required = ['status_name', 'status_type']
        if not all(k in data for k in required):
            raise ValueError("Missing required fields")
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO status (status_name, status_type, description)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(sql, (
                    data['status_name'],
                    data['status_type'],
                    data.get('description', '')
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_status(self, status_id: int, data: Dict) -> bool:
        """Обновить статус"""
        allowed_fields = ['status_name', 'status_type', 'description']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        set_clause = ", ".join([f"{k} = %s" for k in update_fields.keys()])
        sql = f"UPDATE status SET {set_clause} WHERE status_id = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(update_fields.values()) + [status_id])
                conn.commit()
                return cursor.rowcount > 0
    
    def delete_status(self, status_id: int) -> bool:
        """Удалить статус"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Проверяем связанные сессии
                cursor.execute("SELECT COUNT(*) as count FROM session WHERE status_id = %s", (status_id,))
                if cursor.fetchone()['count'] > 0:
                    raise ValueError("Cannot delete status with assigned sessions")
                
                cursor.execute("DELETE FROM status WHERE status_id = %s", (status_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    # =========================================================================
    # ДАШБОРД / СТАТИСТИКА
    # =========================================================================
    
    def get_dashboard_stats(self) -> Dict:
        """Получить общую статистику для дашборда"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Общее количество компьютеров
                cursor.execute("SELECT COUNT(*) as count, SUM(is_online) as online FROM computer")
                comp_stats = cursor.fetchone()
                
                # Общее количество пользователей
                cursor.execute("SELECT COUNT(*) as count FROM user WHERE is_active = 1")
                user_stats = cursor.fetchone()
                
                # Активные сессии
                cursor.execute("SELECT COUNT(*) as count FROM session WHERE status_id = 1")
                active_sessions = cursor.fetchone()
                
                # Сессии за последние 24 часа
                cursor.execute("""
                    SELECT COUNT(*) as count FROM session 
                    WHERE start_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                """)
                sessions_24h = cursor.fetchone()
                
                # Компьютеры по типам ОС
                cursor.execute("""
                    SELECT os.os_name, COUNT(*) as count 
                    FROM computer c
                    LEFT JOIN operating_system os ON c.os_id = os.os_id
                    GROUP BY os.os_name
                """)
                by_os = cursor.fetchall()
                
                # Компьютеры онлайн/офлайн
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN is_online = 1 THEN 1 ELSE 0 END) as online,
                        SUM(CASE WHEN is_online = 0 THEN 1 ELSE 0 END) as offline
                    FROM computer
                """)
                online_stats = cursor.fetchone()
                
                return {
                    'total_computers': comp_stats['count'] or 0,
                    'online_computers': online_stats['online'] or 0,
                    'offline_computers': online_stats['offline'] or 0,
                    'total_users': user_stats['count'] or 0,
                    'active_sessions': active_sessions['count'] or 0,
                    'sessions_24h': sessions_24h['count'] or 0,
                    'by_operating_system': by_os
                }
    
    def get_activity_timeline(
        self,
        from_date: datetime,
        to_date: datetime,
        group_by: str = 'hour'
    ) -> List[Dict]:
        """Получить timeline активности"""
        if group_by == 'hour':
            date_format = '%Y-%m-%d %H:00'
        elif group_by == 'day':
            date_format = '%Y-%m-%d'
        else:
            date_format = '%Y-%m-%d'
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = f"""
                    SELECT 
                        DATE_FORMAT(start_time, %s) as time_bucket,
                        COUNT(*) as session_count,
                        COUNT(DISTINCT computer_id) as unique_computers
                    FROM session
                    WHERE start_time >= %s AND start_time <= %s
                    GROUP BY time_bucket
                    ORDER BY time_bucket
                """
                cursor.execute(sql, (date_format, from_date, to_date))
                return cursor.fetchall()
    
    def get_top_users(self, limit: int = 10) -> List[Dict]:
        """Получить топ пользователей по активности"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        u.user_id,
                        u.login,
                        u.full_name,
                        r.role_name,
                        COUNT(s.session_id) as session_count,
                        MAX(s.start_time) as last_session
                    FROM user u
                    LEFT JOIN role r ON u.role_id = r.role_id
                    LEFT JOIN computer c ON c.user_id = u.user_id
                    LEFT JOIN session s ON s.computer_id = c.computer_id
                    WHERE u.is_active = 1
                    GROUP BY u.user_id, u.login, u.full_name, r.role_name
                    ORDER BY session_count DESC
                    LIMIT %s
                """
                cursor.execute(sql, (limit,))
                return cursor.fetchall()
