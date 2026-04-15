import hashlib
import socket
import os
import sys
import json
import traceback
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QFrame, QProgressBar, QMessageBox, QPushButton,
                            QLineEdit, QApplication, QComboBox, QCheckBox, QWidget, QSpacerItem)
from PyQt6.QtCore import Qt, QTimer, QSettings, QEvent
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor

from core.hardware_id import HardwareIDGenerator
from core.api_client import APIClient as DatabaseManager
from utils.platform_utils import get_config_dir


class CustomEvent(QEvent):
    """Кастомное событие для передачи данных между потоками"""
    def __init__(self, event_type: str, data: dict = None):
        super().__init__(QEvent.Type.User + 1)
        self.event_type = event_type
        self.data = data or {}


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения (кроссплатформенно)"""
    icon_path = Path(__file__).parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    icon_path = Path(__file__).parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(255, 140, 66))
    return QIcon(pixmap)


def get_base_path() -> Path:
    """Возвращает корневую папку приложения"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


class AuthDialog(QDialog):
    """Главный диалог авторизации с переключением между входом и регистрацией"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.computer_data = None
        self.auth_success = False
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.init_ui()
        QTimer.singleShot(100, self.load_saved_credentials)
    
    def load_saved_credentials(self):
        """Загружает сохранённые учётные данные и пытается автоматически войти"""
        settings = QSettings("RemoteAccess", "Agent")
        auto_auth = settings.value("auto_auth", False, type=bool)
        
        if auto_auth:
            try:
                config_dir = get_config_dir()
                cred_file = config_dir / "credentials.txt"
                if cred_file.exists():
                    with open(cred_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    login = None
                    password = None
                    for line in content.split('\n'):
                        if line.startswith('Login:'):
                            login = line.split(':', 1)[1].strip()
                        elif line.startswith('Password:'):
                            password = line.split(':', 1)[1].strip()
                    
                    if login and password:
                        self.do_auto_login(login, password)
            except Exception as e:
                print(f"Ошибка загрузки сохранённых данных: {e}")
        else:
            self.login_edit.setEnabled(True)
            self.password_edit.setEnabled(True)
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(450, 400)
        self.setStyleSheet("""
            QDialog { background-color: white; border-radius: 8px; }
            QLabel { color: #333333; }
            QLineEdit {
                border: 1px solid #ff8c42;
                border-radius: 4px;
                padding: 6px;
                font-size: 14px;
            }
            #loginBtn {
                color: white;
                background-color: #ff8c42;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }
            #loginBtn:hover { background-color: #ff6b2c; }
            #registerBtn {
                color: white;
                background-color: #27ae60;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }
            #registerBtn:hover { background-color: #219a52; }
            #backBtn {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }
            #backBtn:hover { background-color: #7f8c8d; }
            QMessageBox QPushButton {
                color: #333333;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(25, 25, 25, 25)
        
        # Заголовок
        self.title_frame = QFrame()
        self.title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 8px;")
        self.title_layout = QHBoxLayout(self.title_frame)
        self.title_layout.setContentsMargins(15, 25, 15, 25)
        self.title_label = QLabel("⚡ REMOTE ACCESS AGENT")
        self.title_label.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.title_frame)
        
        # Пустое пространство после заголовка
        spacer = QSpacerItem(0, 20)
        self.main_layout.addSpacerItem(spacer)
        
        # Приветствие
        self.welcome_label = QLabel("Добро пожаловать! Войдите в систему")
        self.welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_label.setStyleSheet("color: #ff8c42; font-size: 14px; font-weight: bold;")
        self.main_layout.addWidget(self.welcome_label)
        
        # Подсказка для регистрации
        self.hint_label = QLabel("При необходимости измените логин и пароль:")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("color: #666; font-size: 13px;")
        self.hint_label.setVisible(False)
        self.main_layout.addWidget(self.hint_label)
        
        # Поля входа
        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("Логин")
        self.login_edit.setMinimumHeight(38)
        self.login_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.login_edit)
        
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Пароль")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setMinimumHeight(38)
        self.password_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.password_edit.returnPressed.connect(self.do_login)
        self.main_layout.addWidget(self.password_edit)
        
        # Поля регистрации
        self.reg_login_edit = QLineEdit()
        self.reg_login_edit.setPlaceholderText("Логин")
        self.reg_login_edit.setMinimumHeight(38)
        self.reg_login_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reg_login_edit.setVisible(False)
        self.main_layout.addWidget(self.reg_login_edit)
        
        self.reg_password_edit = QLineEdit()
        self.reg_password_edit.setPlaceholderText("Пароль")
        self.reg_password_edit.setMinimumHeight(38)
        self.reg_password_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reg_password_edit.setVisible(False)
        self.main_layout.addWidget(self.reg_password_edit)
        
        self.validation_label = QLabel("")
        self.validation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.validation_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self.main_layout.addWidget(self.validation_label)
        
        # Кнопки
        self.login_btn = QPushButton("Войти")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.setMinimumHeight(40)
        self.login_btn.clicked.connect(self.do_login)
        self.main_layout.addWidget(self.login_btn)
        
        self.reg_btn = QPushButton("Зарегистрировать")
        self.reg_btn.setObjectName("registerBtn")
        self.reg_btn.setMinimumHeight(40)
        self.reg_btn.clicked.connect(self.do_register)
        self.reg_btn.setVisible(False)
        self.main_layout.addWidget(self.reg_btn)
        
        # Статус и ошибка
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; font-size: 13px;")
        self.status_label.setVisible(False)
        self.main_layout.addWidget(self.status_label)
        
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.main_layout.addWidget(self.error_label)
        
        # Кнопки переключения
        self.register_link_btn = QPushButton("Зарегистрироваться")
        self.register_link_btn.setObjectName("registerBtn")
        self.register_link_btn.setMinimumHeight(38)
        self.register_link_btn.clicked.connect(self.show_register_form)
        self.main_layout.addWidget(self.register_link_btn)
        
        # Скрываем кнопку регистрации если уже есть учётные данные
        self.check_credentials_and_hide_register()
    
    def check_credentials_and_hide_register(self):
        """Проверяет наличие файла учётных данных и скрывает кнопку регистрации"""
        try:
            config_dir = get_config_dir()
            cred_file = config_dir / "credentials.txt"
            if cred_file.exists():
                self.register_link_btn.setVisible(False)
        except Exception as e:
            print(f"Ошибка проверки учётных данных: {e}")
        
        self.back_btn = QPushButton("Назад к входу")
        self.back_btn.setObjectName("backBtn")
        self.back_btn.setMinimumHeight(38)
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self.show_login_form)
        self.main_layout.addWidget(self.back_btn)
    
    def show_register_form(self):
        """Переключает на форму регистрации"""
        computer_name = socket.gethostname()
        self.reg_login_edit.setText(computer_name.lower().replace('-', '_').replace(' ', '_')[:20])
        # Генерируем новый пароль при каждом открытии формы регистрации
        self.reg_password_edit.setText(HardwareIDGenerator.generate_unique_id()[:12])
        # Сохраняем пароль для регистрации, но не показываем его повторно
        self._temp_password = self.reg_password_edit.text()
        
        self.title_frame.setStyleSheet("background-color: #27ae60; border-radius: 8px;")
        self.welcome_label.setText("Создайте аккаунт для регистрации")
        self.welcome_label.setStyleSheet("color: #27ae60; font-size: 14px; font-weight: bold;")
        
        self.login_edit.setVisible(False)
        self.password_edit.setVisible(False)
        self.login_btn.setVisible(False)
        self.register_link_btn.setVisible(False)
        
        self.hint_label.setVisible(True)
        self.reg_login_edit.setVisible(True)
        self.reg_password_edit.setVisible(True)
        self.reg_btn.setVisible(True)
        self.back_btn.setVisible(True)
        self.error_label.setVisible(False)
        self.status_label.setVisible(False)
    
    def show_login_form(self):
        """Переключает на форму входа"""
        self.title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 8px;")
        self.welcome_label.setText("Добро пожаловать! Войдите в систему")
        self.welcome_label.setStyleSheet("color: #ff8c42; font-size: 14px; font-weight: bold;")
        
        self.hint_label.setVisible(False)
        self.reg_login_edit.setVisible(False)
        self.reg_password_edit.setVisible(False)
        self.reg_btn.setVisible(False)
        
        # Очищаем данные регистрации при переходе на форму входа
        self.reg_login_edit.clear()
        self.reg_password_edit.clear()
        if hasattr(self, '_temp_password'):
            delattr(self, '_temp_password')
        
        self.login_edit.setVisible(True)
        self.password_edit.setVisible(True)
        self.login_btn.setVisible(True)
        self.back_btn.setVisible(False)
        self.register_link_btn.setVisible(True)
        self.error_label.setVisible(False)
        self.status_label.setVisible(False)
    
    def do_auto_login(self, login: str, password: str):
        """Автоматический вход с сохранёнными данными"""
        try:
            user_data = DatabaseManager.login(login, password)
            
            if not user_data:
                return
            
            user_id = user_data['user_id']
            role_id = user_data.get('role_id')
            is_admin = role_id in (2, 3) or str(role_id) in ('2', '3')
            
            # Подключаем компьютер
            computer_result = DatabaseManager.register_computer_for_user(user_id)
            
            if not computer_result:
                return
            
            computer_id = computer_result['computer_id']
            hostname = socket.gethostname()
            mac_address = HardwareIDGenerator.get_mac_address()
            
            # Если компьютер уже был привязан к другому пользователю - перепривязываем
            if computer_result.get('already_bound') and computer_result.get('other_user_id'):
                other_user_id = computer_result.get('other_user_id')
                print(f"⚠️ Компьютер был привязан к пользователю {other_user_id}")
                
                # Перепривязываем компьютер к текущему пользователю
                rebind_result = DatabaseManager.rebind_computer(
                    computer_id=computer_id,
                    user_id=user_id,
                    computer_type='admin' if is_admin else 'client'
                )
                
                if not rebind_result:
                    print(f"⚠️ Не удалось перепривязать компьютер, но продолжаем")
            
            session_id = None
            session_token = DatabaseManager.auth_token
            
            self.computer_data = {
                'computer_id': computer_id,
                'hostname': hostname,
                'mac_address': mac_address,
                'login': login,
                'password': password,
                'user_id': user_id,
                'role_id': role_id,
                'computer_type': 'admin' if is_admin else 'client',
                'session_id': session_id,
                'session_token': session_token,
                'is_new': False,
                'hardware_changed': False
            }
            
            self.auth_success = True
            self.accept()
                
        except Exception as e:
            print(f"Ошибка автоматического входа: {e}")
    
    def do_login(self):
        """Выполняем вход и регистрацию компьютера"""
        login = self.login_edit.text().strip()
        password = self.password_edit.text().strip()
        
        if not login or not password:
            self.show_error("Введите логин и пароль")
            return
        
        self.login_edit.setEnabled(False)
        self.password_edit.setEnabled(False)
        self.login_btn.setEnabled(False)
        
        self.status_label.setText("Проверка учетных данных...")
        self.status_label.setVisible(True)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; font-size: 11px;")
        self.error_label.setVisible(False)
        QApplication.processEvents()
        
        try:
            # Аутентификация через API
            user_data = DatabaseManager.login(login, password)
            
            if not user_data:
                raise Exception("Неверный логин или пароль")
            
            user_id = user_data['user_id']
            role_id = user_data.get('role_id')
            is_admin = role_id in (2, 3) or str(role_id) in ('2', '3')
            
            self.status_label.setText("Регистрация компьютера...")
            QApplication.processEvents()
            
            computer_result = DatabaseManager.register_computer_for_user(user_id)
            
            if not computer_result:
                raise Exception("Не удалось зарегистрировать компьютер")
            
            computer_id = computer_result['computer_id']
            hostname = computer_result['hostname']
            mac_address = computer_result.get('mac_address', '')
            
            # Если компьютер уже был привязан к другому пользователю - перепривязываем
            if computer_result.get('already_bound') and computer_result.get('other_user_id'):
                other_user_id = computer_result.get('other_user_id')
                other_user_login = computer_result.get('other_user_login', 'Unknown')
                print(f"⚠️ Компьютер был привязан к пользователю {other_user_login} (ID: {other_user_id})")
                
                # Перепривязываем компьютер к текущему пользователю
                self.status_label.setText("Перепривязка компьютера...")
                QApplication.processEvents()
                
                rebind_result = DatabaseManager.rebind_computer(
                    computer_id=computer_id,
                    user_id=user_id,
                    computer_type='admin' if is_admin else 'client'
                )
                
                if not rebind_result:
                    print(f"⚠️ Не удалось перепривязать компьютер, но продолжаем")
                else:
                    print(f"✅ Компьютер успешно перепривязан к {login}")
            
            session_id = computer_result.get('session_id')
            session_token = DatabaseManager.auth_token
            
            self.computer_data = {
                'computer_id': computer_id,
                'hostname': hostname,
                'mac_address': mac_address,
                'login': login,
                'password': password,
                'user_id': user_id,
                'role_id': role_id,
                'computer_type': 'admin' if is_admin else 'client',
                'session_id': session_id,
                'session_token': session_token,
                'is_new': computer_result.get('is_new', False),
                'hardware_changed': computer_result.get('hardware_changed', False)
            }
            
            self.save_credentials(self.computer_data)
            
            settings = QSettings("RemoteAccess", "Agent")
            settings.setValue("auto_auth", True)
            settings.sync()
            
            self.auth_success = True
            self.accept()
            
        except Exception as e:
            error_msg = str(e)
            print(f"Ошибка авторизации: {error_msg}")
            self.show_error(error_msg)
            
            self.login_edit.setEnabled(True)
            self.password_edit.setEnabled(True)
            self.login_btn.setEnabled(True)
            self.status_label.setVisible(False)
    
    def do_register(self):
        """Выполняет регистрацию нового клиента"""
        login = self.reg_login_edit.text().strip()
        password = self.reg_password_edit.text().strip()
        
        if not login:
            self.show_register_error("Введите логин")
            return
        if not password:
            self.show_register_error("Введите пароль")
            return
        if len(password) < 4:
            self.show_register_error("Пароль не менее 4 символов")
            return
        
        self.status_label.setText("Создание аккаунта...")
        self.status_label.setVisible(True)
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 11px;")
        self.error_label.setVisible(False)
        self.validation_label.setText("")
        QApplication.processEvents()
        
        try:
            # Проверяем существование пользователя через API
            existing = DatabaseManager.get_users()
            if existing:
                for user in existing.get('users', []):
                    if user.get('login') == login:
                        raise Exception("Логин уже занят")
            
            user_id = DatabaseManager.create_user(login, password, login, 'client')
            
            if not user_id:
                raise Exception("Не удалось создать пользователя")
            
            self.status_label.setText("Регистрация компьютера...")
            QApplication.processEvents()
            
            computer_result = DatabaseManager.register_computer_for_user(user_id)
            
            if not computer_result:
                raise Exception("Не удалось зарегистрировать компьютер")
            
            computer_id = computer_result['computer_id']
            hostname = computer_result['hostname']
            mac_address = computer_result['mac_address']
            
            session_id = computer_result.get('session_id')
            session_token = DatabaseManager.auth_token
            
            self.computer_data = {
                'computer_id': computer_id,
                'hostname': hostname,
                'mac_address': mac_address,
                'login': login,
                'password': password,
                'user_id': user_id,
                'role_id': 1,
                'computer_type': 'client',
                'session_id': session_id,
                'session_token': session_token,
                'is_new': computer_result.get('is_new', False),
                'hardware_changed': computer_result.get('hardware_changed', False)
            }
            
            self.save_credentials(self.computer_data)
            
            settings = QSettings("RemoteAccess", "Agent")
            settings.setValue("auto_auth", True)
            settings.sync()
            
            self.auth_success = True
            self.accept()
            
        except Exception as e:
            error_msg = str(e)
            print(f"Ошибка регистрации: {error_msg}")
            self.show_register_error(error_msg)
            self.status_label.setVisible(False)
    
    def show_error(self, message: str):
        self.error_label.setText(f"❌ {message}")
        self.error_label.setVisible(True)
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 11px;")
    
    def show_register_error(self, message: str):
        self.error_label.setText(f"❌ {message}")
        self.error_label.setVisible(True)
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 11px;")
    
    def save_credentials(self, computer_data: dict):
        # Не сохраняем данные для админа - только для клиента
        computer_type = computer_data.get('computer_type', 'client')
        if computer_type == 'admin':
            print("Администратор вошёл в систему - учётные данные не сохраняются")
            return
            
        try:
            config_dir = get_config_dir()
            cred_file = config_dir / "credentials.txt"
            
            # Сохраняем только логин и пароль
            with open(cred_file, 'w', encoding='utf-8') as f:
                f.write(f"Login: {computer_data['login']}\n")
                f.write(f"Password: {computer_data.get('password', '')}\n")
            
            print(f"Учетные данные сохранены в: {cred_file}")
            
        except Exception as e:
            print(f"Ошибка сохранения учетных данных: {e}")
    
    def get_computer_data(self):
        return self.computer_data
    
    def is_auth_success(self):
        return self.auth_success


class HardwareRegisterDialog(QDialog):
    """Диалог регистрации железа"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registration_data = None
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(450, 350)
        self.setStyleSheet("""
            QDialog { background-color: white; border-radius: 10px; }
            QLabel { color: #333333; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 15px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        layout.addWidget(title_frame)
        
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid #ff8c42; border-radius: 8px; padding: 15px;")
        info_layout = QVBoxLayout(info_frame)
        
        computer_name = socket.gethostname()
        info_text = f"""
        <div style='text-align: center;'>
            <h3 style='color: #ff8c42;'>Регистрация оборудования</h3>
            <p><b>Компьютер:</b> {computer_name}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
            <br>
            <p>Выполняется регистрация оборудования...</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_frame)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ff8c42;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #ff8c42;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Подключение к базе данных...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)
        
        QTimer.singleShot(500, self.do_register)
    
    def do_register(self):
        try:
            self.status_label.setText("Регистрация оборудования...")
            QApplication.processEvents()
            
            dialog = AuthDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.registration_data = dialog.get_computer_data()
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                QTimer.singleShot(500, self.accept)
            else:
                self.status_label.setText("Регистрация отменена")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                self.progress_bar.setVisible(False)
                QTimer.singleShot(2000, self.reject)
                
        except Exception as e:
            print(f"Ошибка регистрации: {e}")
            print(traceback.format_exc())
            self.status_label.setText(f"Ошибка: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.progress_bar.setVisible(False)
            QTimer.singleShot(2000, self.reject)
    
    def get_registration_data(self):
        return self.registration_data


class ClientAuthDialog(QDialog):
    """Диалог авторизации клиента"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.computer_data = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle("Вход клиента")
        self.setFixedSize(450, 400)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background-color: white; border-radius: 10px; }
            QLabel { color: #333333; }
            QLineEdit {
                border: 1px solid #ff8c42;
                border-radius: 4px;
                padding: 8px;
                margin: 5px;
            }
            QPushButton {
                background-color: #ff8c42;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff6b2c; }
            QPushButton#cancelBtn {
                background-color: #e74c3c;
            }
            QPushButton#cancelBtn:hover {
                background-color: #c0392b;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        title = QLabel("ВХОД КЛИЕНТА")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; padding: 12px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        layout.addWidget(title_frame)
        
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid #ff8c42; border-radius: 8px; padding: 10px;")
        info_layout = QVBoxLayout(info_frame)
        
        computer_name = socket.gethostname()
        info_text = f"""
        <div style='text-align: center;'>
            <p><b>Компьютер:</b> {computer_name}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
            <p style='color: #ff8c42;'>Введите ваши учетные данные</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_frame)
        
        form_frame = QFrame()
        form_layout = QVBoxLayout(form_frame)
        
        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("Логин")
        self.login_edit.setMinimumHeight(35)
        form_layout.addWidget(self.login_edit)
        
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Пароль")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setMinimumHeight(35)
        form_layout.addWidget(self.password_edit)
        
        layout.addWidget(form_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        login_btn = QPushButton("Войти")
        login_btn.setMinimumHeight(40)
        login_btn.clicked.connect(self.do_login)
        btn_layout.addWidget(login_btn)
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
    
    def do_login(self):
        login = self.login_edit.text().strip()
        password = self.password_edit.text().strip()
        
        if not login or not password:
            self.error_label.setText("Введите логин и пароль")
            return
        
        try:
            dialog = AuthDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.computer_data = dialog.get_computer_data()
                self.accept()
            else:
                self.error_label.setText("Авторизация отменена")
                
        except Exception as e:
            self.error_label.setText(f"Ошибка: {str(e)}")
    
    def get_computer_data(self):
        return self.computer_data