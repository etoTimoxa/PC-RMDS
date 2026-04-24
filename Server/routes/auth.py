"""
Auth routes - Авторизация и регистрация пользователей
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import jwt
import hashlib

# Фикс для PyJWT 3.x
jwt.encode = getattr(jwt, 'encode', jwt.encode)
jwt.decode = getattr(jwt, 'decode', jwt.decode)

from config import API_CONFIG
from services.mysql_service import MySQLService

auth_bp = Blueprint('auth', __name__)
mysql = MySQLService()

JWT_SECRET = API_CONFIG.get('jwt_secret', 'pc-rmds-secret-key-2026')
JWT_EXPIRE_HOURS = 24


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    POST /api/auth/register
    Регистрация нового пользователя
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Нет данных для регистрации'
            }), 400

        required_fields = ['login', 'password', 'full_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400

        # Проверяем что пользователь с таким логином не существует
        existing = mysql.fetch_one(
            "SELECT user_id FROM user WHERE login = %s", 
            (data['login'],)
        )
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'Пользователь с таким логином уже существует'
            }), 409

        # Хешируем пароль (SHA256 как в базе)
        password_hash = hashlib.sha256(data['password'].encode()).hexdigest()

        user_id = mysql.execute("""
            INSERT INTO user (login, password_hash, full_name, role_id, is_active, created_at)
            VALUES (%s, %s, %s, 1, 1, NOW())
        """, (
            data['login'],
            password_hash,
            data['full_name']
        ))

        return jsonify({
            'success': True,
            'message': 'Пользователь успешно зарегистрирован',
            'data': {
                'user_id': user_id
            }
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    POST /api/auth/login
    Авторизация пользователя, получение JWT токена
    """
    user_id = None
    login = None
    full_name = None
    role_id = None
    
    try:
        data = request.get_json()
        
        if not data or 'login' not in data or 'password' not in data:
            return jsonify({
                'success': False,
                'error': 'Требуется логин и пароль'
            }), 400

        user = mysql.fetch_one(
            "SELECT user_id, login, full_name, password_hash, role_id, is_active FROM user WHERE login = %s",
            (data['login'],)
        )

        if not user:
            return jsonify({
                'success': False,
                'error': 'Неверный логин или пароль'
            }), 401

        if not user['is_active']:
            return jsonify({
                'success': False,
                'error': 'Пользователь заблокирован'
            }), 403

        # Проверяем пароль (хеш в базе SHA256)
        password_hash = hashlib.sha256(data['password'].encode()).hexdigest()
        
        if password_hash != user['password_hash']:
            return jsonify({
                'success': False,
                'error': 'Неверный логин или пароль'
            }), 401

        # Генерируем JWT токен
        user_id = user['user_id']
        login = user['login']
        full_name = user['full_name']
        role_id = user['role_id']
        
        payload = {
            'user_id': user_id,
            'login': login,
            'role_id': role_id,
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

        return jsonify({
            'success': True,
            'data': {
                'token': token,
                'user': {
                    'user_id': user_id,
                    'login': login,
                    'full_name': full_name,
                    'role_id': role_id,
                    'is_admin': role_id in (2, 3)
                }
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """
    GET /api/auth/me
    Получить информацию о текущем авторизованном пользователе
    """
    try:
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': 'Требуется авторизация'
            }), 401

        token = auth_header.split(' ')[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])

        user = mysql.fetch_one("""
            SELECT user_id, login, full_name, role_id, is_active, created_at 
            FROM user WHERE user_id = %s
        """, (payload['user_id'],))

        return jsonify({
            'success': True,
            'data': user
        })

    except jwt.ExpiredSignatureError:
        return jsonify({
            'success': False,
            'error': 'Сессия истекла, требуется повторная авторизация'
        }), 401
    except jwt.InvalidTokenError:
        return jsonify({
            'success': False,
            'error': 'Неверный токен авторизации'
        }), 401
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    POST /api/auth/logout
    Выход из системы
    """
    return jsonify({
        'success': True,
        'message': 'Успешный выход из системы'
    })


@auth_bp.route('/password/reset-request', methods=['POST'])
def password_reset_request():
    """
    POST /api/auth/password/reset-request
    Запрос на сброс пароля
    Принимает логин пользователя, генерирует токен сброса пароля
    """
    try:
        data = request.get_json()
        
        if not data or 'login' not in data:
            return jsonify({
                'success': False,
                'error': 'Требуется указать логин пользователя'
            }), 400

        # Проверяем существование пользователя
        user = mysql.fetch_one(
            "SELECT user_id, login, is_active FROM user WHERE login = %s",
            (data['login'],)
        )

        # В целях безопасности всегда возвращаем одинаковый ответ даже если пользователь не найден
        if not user:
            return jsonify({
                'success': True,
                'message': 'Если пользователь существует, токен для сброса пароля был сгенерирован'
            })

        if not user['is_active']:
            return jsonify({
                'success': False,
                'error': 'Пользователь заблокирован'
            }), 403

        # Генерируем токен сброса пароля (действителен 1 час)
        payload = {
            'user_id': user['user_id'],
            'type': 'password_reset',
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        
        reset_token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

        # TODO: Здесь в будущем добавить отправку токена на email пользователя
        # В текущей версии возвращаем токен напрямую для отладки
        return jsonify({
            'success': True,
            'message': 'Токен для сброса пароля сгенерирован',
            'data': {
                'reset_token': reset_token,
                'expires_in': 3600
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@auth_bp.route('/password/reset', methods=['POST'])
def password_reset():
    """
    POST /api/auth/password/reset
    Сброс пароля по токену
    Принимает токен сброса и новый пароль
    """
    try:
        data = request.get_json()
        
        required_fields = ['reset_token', 'new_password']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Отсутствует обязательное поле: {field}'
                }), 400

        # Проверяем и декодируем токен
        try:
            payload = jwt.decode(data['reset_token'], JWT_SECRET, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({
                'success': False,
                'error': 'Токен сброса пароля истек'
            }), 401
        except jwt.InvalidTokenError:
            return jsonify({
                'success': False,
                'error': 'Неверный токен сброса пароля'
            }), 401

        # Проверяем тип токена
        if payload.get('type') != 'password_reset':
            return jsonify({
                'success': False,
                'error': 'Некорректный тип токена'
            }), 400

        # Проверяем что пользователь существует и активен
        user = mysql.fetch_one(
            "SELECT user_id, is_active FROM user WHERE user_id = %s",
            (payload['user_id'],)
        )

        if not user:
            return jsonify({
                'success': False,
                'error': 'Пользователь не найден'
            }), 404

        if not user['is_active']:
            return jsonify({
                'success': False,
                'error': 'Пользователь заблокирован'
            }), 403

        # Хешируем новый пароль
        new_password_hash = hashlib.sha256(data['new_password'].encode()).hexdigest()

        # Обновляем пароль в базе
        mysql.execute("""
            UPDATE user 
            SET password_hash = %s, updated_at = NOW()
            WHERE user_id = %s
        """, (new_password_hash, user['user_id']))

        return jsonify({
            'success': True,
            'message': 'Пароль успешно изменен'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
