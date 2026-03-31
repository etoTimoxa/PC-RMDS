import socket
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QFrame, QProgressBar, QMessageBox, QPushButton,
                            QLineEdit, QApplication)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor

from core.hardware_id import HardwareIDGenerator
from core.database_manager import DatabaseManager
from utils.platform_utils import get_config_dir


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения (кроссплатформенно)"""
    # Пробуем PNG (для Linux/AppImage)
    icon_path = Path(__file__).parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    # Пробуем ICO (для Windows)
    icon_path = Path(__file__).parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    # Если иконка не найдена, создаем цветной квадрат
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(255, 140, 66))
    return QIcon(pixmap)


def get_base_path() -> Path:
    """Возвращает корневую папку приложения"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


class AuthChoiceDialog(QDialog):
    """Главный диалог выбора способа входа"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle("Выбор способа входа")
        self.setFixedSize(450, 350)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background-color: white; border-radius: 10px; }
            QLabel { color: #333333; }
            QPushButton { 
                background-color: #ff8c42; 
                color: white; 
                border: none; 
                padding: 10px; 
                border-radius: 6px;
                font-weight: bold;
                min-width: 150px;
            }
            QPushButton:hover { background-color: #ff6b2c; }
            QPushButton#manualBtn {
                background-color: #3498db;
            }
            QPushButton#manualBtn:hover {
                background-color: #2980b9;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Заголовок
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 15px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        layout.addWidget(title_frame)
        
        # Информация
        info_text = f"""
        <div style='text-align: center;'>
            <h3 style='color: #ff8c42;'>Выберите способ входа</h3>
            <p><b>Компьютер:</b> {socket.gethostname()}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
            <br>
            <p>Выберите, как вы хотите авторизоваться в системе:</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Кнопки
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        
        auto_btn = QPushButton("🔐 Автоматическая регистрация по железу")
        auto_btn.setMinimumHeight(45)
        auto_btn.clicked.connect(lambda: self.on_choice('auto'))
        btn_layout.addWidget(auto_btn)
        
        manual_btn = QPushButton("👤 Ручной вход (логин/пароль)")
        manual_btn.setObjectName("manualBtn")
        manual_btn.setMinimumHeight(45)
        manual_btn.clicked.connect(lambda: self.on_choice('manual'))
        btn_layout.addWidget(manual_btn)
        
        layout.addLayout(btn_layout)
    
    def on_choice(self, choice: str):
        self.choice = choice
        self.accept()
    
    def get_choice(self):
        return self.choice


class ManualAuthDialog(QDialog):
    """Диалог ручного входа"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.computer_data = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle("Ручной вход")
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
        
        # Заголовок
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        title = QLabel("🔑 РУЧНОЙ ВХОД")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; padding: 12px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        layout.addWidget(title_frame)
        
        # Информация
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
        
        # Форма входа
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
        
        # Кнопки
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
            computer_data = DatabaseManager.authenticate_by_credentials(login, password)
            
            if computer_data:
                self.computer_data = computer_data
                self.accept()
            else:
                self.error_label.setText("Неверный логин или пароль")
                
        except Exception as e:
            self.error_label.setText(f"Ошибка: {str(e)}")


class AutoRegisterDialog(QDialog):
    """Диалог автоматической регистрации"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.computer_data = None
        self.auth_success = False
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
        
        # Заголовок
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 15px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        layout.addWidget(title_frame)
        
        # Информация
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid #ff8c42; border-radius: 8px; padding: 15px;")
        info_layout = QVBoxLayout(info_frame)
        
        computer_name = socket.gethostname()
        info_text = f"""
        <div style='text-align: center;'>
            <h3 style='color: #ff8c42;'>Автоматическая регистрация</h3>
            <p><b>Компьютер:</b> {computer_name}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
            <br>
            <p>Выполняется регистрация компьютера...</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_frame)
        
        # Прогресс бар
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
        
        # Статус
        self.status_label = QLabel("Подключение к базе данных...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)
        
        # Запускаем регистрацию
        QTimer.singleShot(500, self.do_register)
    
    def do_register(self):
        """Выполняет регистрацию"""
        try:
            self.status_label.setText("Регистрация компьютера...")
            QApplication.processEvents()
            
            # Регистрируем компьютер
            computer_data = DatabaseManager.register_computer()
            
            if computer_data:
                self.status_label.setText("Регистрация успешна!")
                QApplication.processEvents()
                
                # Сохраняем учетные данные в файл
                self.save_credentials_to_file(computer_data)
                
                # Включаем автоматическую авторизацию для следующих запусков
                settings = QSettings("RemoteAccess", "Agent")
                settings.setValue("auto_auth", True)
                settings.sync()
                
                # Показываем сообщение об успехе
                QMessageBox.information(
                    self,
                    "Регистрация успешна",
                    f"Компьютер успешно зарегистрирован!\n\n"
                    f"ID: {computer_data['computer_id']}\n"
                    f"Логин: {computer_data['login']}\n"
                    f"Пароль: {computer_data['password']}\n"
                    f"MAC адрес: {computer_data['mac_address']}\n\n"
                    f"Учетные данные сохранены в файл:\n{get_config_dir() / 'credentials.txt'}"
                )
                
                self.computer_data = computer_data
                self.auth_success = True
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                
                QTimer.singleShot(1000, self.accept)
            else:
                self.status_label.setText("✗ Ошибка регистрации")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                self.progress_bar.setVisible(False)
                
                QMessageBox.critical(
                    self,
                    "Ошибка",
                    "Не удалось зарегистрировать компьютер.\n"
                    "Проверьте подключение к базе данных."
                )
                
                QTimer.singleShot(2000, self.reject)
                
        except Exception as e:
            print(f"Ошибка регистрации: {e}")
            print(traceback.format_exc())
            self.status_label.setText(f"✗ Ошибка: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.progress_bar.setVisible(False)
            
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка при регистрации:\n{str(e)}"
            )
            
            QTimer.singleShot(2000, self.reject)
    
    def save_credentials_to_file(self, computer_data: dict):
        """Сохраняет учетные данные в файл"""
        try:
            config_dir = get_config_dir()
            cred_file = config_dir / "credentials.txt"
            
            with open(cred_file, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("REMOTE ACCESS CREDENTIALS\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Computer: {computer_data['hostname']}\n")
                f.write(f"Computer ID: {computer_data['computer_id']}\n")
                f.write(f"MAC Address: {computer_data['mac_address']}\n")
                f.write(f"Login: {computer_data['login']}\n")
                f.write(f"Password: {computer_data.get('password', 'N/A')}\n")
                f.write(f"Session Token: {computer_data.get('session_token', 'N/A')}\n")
                f.write("=" * 60 + "\n")
            
            print(f"Учетные данные сохранены в: {cred_file}")
            
        except Exception as e:
            print(f"Ошибка сохранения учетных данных: {e}")


class AuthDialog(QDialog):
    """Главный диалог авторизации - управляет всеми остальными"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.computer_data = None
        self.auth_success = False
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.init_ui()
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(450, 400)
        self.setStyleSheet("""
            QDialog { background-color: white; border-radius: 10px; }
            QLabel { color: #333333; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Заголовок
        title_frame = QFrame()
        title_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        title_layout = QHBoxLayout(title_frame)
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 15px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        layout.addWidget(title_frame)
        
        # Информация
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid #ff8c42; border-radius: 8px; padding: 15px;")
        info_layout = QVBoxLayout(info_frame)
        
        computer_name = socket.gethostname()
        info_text = f"""
        <div style='text-align: center;'>
            <h3 style='color: #ff8c42;'>Авторизация в системе</h3>
            <p><b>Компьютер:</b> {computer_name}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_frame)
        
        # Прогресс бар
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
        
        # Статус
        self.status_label = QLabel("Проверка настроек...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)
        
        # Запускаем проверку
        QTimer.singleShot(500, self.check_auth)
    
    def check_auth(self):
        """Проверяем, нужно ли показывать выбор или уже есть авторизация"""
        try:
            settings = QSettings("RemoteAccess", "Agent")
            auto_auth = settings.value("auto_auth", False, type=bool)
            
            if auto_auth:
                # Пытаемся авторизоваться автоматически
                self.status_label.setText("Автоматическая авторизация...")
                QApplication.processEvents()
                
                computer_data = DatabaseManager.authenticate_computer()
                
                if computer_data:
                    self.computer_data = computer_data
                    self.auth_success = True
                    self.status_label.setText("✓ Авторизация успешна!")
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setValue(100)
                    QTimer.singleShot(500, self.accept)
                    return
                else:
                    # Автоматическая авторизация не удалась, показываем выбор
                    self.show_choice()
                    return
            else:
                # Первый запуск - показываем выбор
                self.show_choice()
                return
                
        except Exception as e:
            print(f"Ошибка: {e}")
            self.status_label.setText(f"✗ Ошибка: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.progress_bar.setVisible(False)
            QTimer.singleShot(2000, self.reject)
    
    def show_choice(self):
        """Показываем диалог выбора способа входа"""
        self.hide()
        
        choice_dialog = AuthChoiceDialog(self.parent())
        if choice_dialog.exec():
            choice = choice_dialog.get_choice()
            if choice == 'auto':
                # Автоматическая регистрация
                self.register_dialog = AutoRegisterDialog(self.parent())
                if self.register_dialog.exec():
                    self.computer_data = self.register_dialog.computer_data
                    self.auth_success = True
                    self.accept()
                else:
                    # Если регистрация не удалась, показываем выбор снова
                    self.show_choice()
            elif choice == 'manual':
                # Ручной вход
                manual_dialog = ManualAuthDialog(self.parent())
                result = manual_dialog.exec()
                
                if result == QDialog.DialogCode.Accepted:
                    # Успешный вход
                    self.computer_data = manual_dialog.computer_data
                    # Включаем автоматическую авторизацию
                    settings = QSettings("RemoteAccess", "Agent")
                    settings.setValue("auto_auth", True)
                    settings.sync()
                    self.auth_success = True
                    self.accept()
                else:
                    # Нажали "Отмена" - возвращаемся к выбору
                    self.show_choice()
        else:
            self.reject()