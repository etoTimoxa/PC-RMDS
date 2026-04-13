"""
Auth routes - Авторизация и регистрация пользователей
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import jwt
import bcrypt

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
            "SELECT user_id FROM users WHERE login = %s", 
            (data['login'],)
        )
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'Пользователь с таким логином уже существует'
            }), 409

        # Хешируем пароль
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), salt)

        user_id = mysql.execute("""
            INSERT INTO users (login, password_hash, full_name, role_id, is_active, created_at)
            VALUES (%s, %s, %s, 2, 1, NOW())
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
    try:
        data = request.get_json()
        
        if not data or 'login' not in data or 'password' not in data:
            return jsonify({
                'success': False,
                'error': 'Требуется логин и пароль'
            }), 400

        user = mysql.fetch_one(
            "SELECT user_id, login, full_name, password_hash, role_id, is_active FROM users WHERE login = %s",
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

        # Проверяем пароль
        if not bcrypt.checkpw(data['password'].encode('utf-8'), user['password_hash'].encode('utf-8')):
            return jsonify({
                'success': False,
                'error': 'Неверный логин или пароль'
            }), 401

        # Генерируем JWT токен
        payload = {
            'user_id': user['user_id'],
            'login': user['login'],
            'role_id': user['role_id'],
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

        return jsonify({
            'success': True,
            'data': {
                'token': token,
                'user': {
                    'user_id': user['user_id'],
                    'login': user['login'],
                    'full_name': user['full_name'],
                    'role_id': user['role_id']
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
            FROM users WHERE user_id = %s
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