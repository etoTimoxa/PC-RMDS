import socket
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QFrame, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QTimer

from core.hardware_id import HardwareIDGenerator
from core.database_manager import DatabaseManager


class AutoAuthDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_success = False
        self.computer_data = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
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
            <h3 style='color: #ff8c42;'>Автоматическая авторизация в системе</h3>
            <p><b>Компьютер:</b> {computer_name}</p>
            <p><b>MAC адрес:</b> {HardwareIDGenerator.get_mac_address()}</p>
            <p><b>Статус:</b> Выполняется регистрация...</p>
        </div>
        """
        
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_frame)
        
        # Прогресс
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
        self.status_label = QLabel("Регистрация...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #ff8c42; font-weight: bold; padding: 5px;")
        layout.addWidget(self.status_label)
        
        QTimer.singleShot(500, self.register)
    
    def register(self):
        self.status_label.setText("Проверка регистрации...")
        QTimer.singleShot(100, self.do_register)
    
    def do_register(self):
        try:
            computer_data = DatabaseManager.authenticate_computer()
            
            if not computer_data:
                self.status_label.setText("Регистрация нового компьютера...")
                computer_data = DatabaseManager.register_computer()
            
            if computer_data:
                self.computer_data = computer_data
                self.auth_success = True
                self.status_label.setText("✓ Регистрация успешна!")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                
                if computer_data.get('is_new'):
                    QMessageBox.information(
                        self,
                        "Регистрация успешна",
                        f"Компьютер зарегистрирован!\n\n"
                        f"ID: {computer_data['computer_id']}\n"
                        f"Логин: {computer_data['login']}\n"
                        f"Токен сессии: {computer_data.get('session_token', 'N/A')}\n\n"
                        f"Данные сохранены в:\n~/remote_access_credentials.txt"
                    )
                
                QTimer.singleShot(1000, self.accept)
            else:
                self.status_label.setText("✗ Ошибка подключения к БД")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                QTimer.singleShot(3000, self.reject)
                
        except Exception as e:
            self.status_label.setText(f"✗ Ошибка: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            QTimer.singleShot(3000, self.reject)