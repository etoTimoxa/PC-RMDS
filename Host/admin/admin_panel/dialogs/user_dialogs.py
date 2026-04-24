"""Диалоги для работы с пользователями"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QFormLayout, QMessageBox, QCheckBox)
from PyQt6.QtCore import Qt

from core.api_client import APIClient as DatabaseManager


class EditUserDialog(QDialog):
    """Диалог редактирования пользователя"""
    
    def __init__(self, user_data, parent=None):
        super().__init__(parent)
        self.user_data = user_data
        self.init_ui()
        self.fill_data()
    
    def init_ui(self):
        self.setWindowTitle("Редактирование пользователя")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.login_input = QLineEdit()
        form_layout.addRow("Логин:", self.login_input)
        
        self.full_name_input = QLineEdit()
        form_layout.addRow("Полное имя:", self.full_name_input)
        
        
        self.role_combo = QComboBox()
        self.role_combo.addItems(["user", "admin", "manager"])
        form_layout.addRow("Роль:", self.role_combo)
        
        self.active_checkbox = QCheckBox("Активен")
        form_layout.addRow(self.active_checkbox)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Сохранить")
        save_btn.setStyleSheet("background-color: #27ae60; color: white;")
        save_btn.clicked.connect(self.save_changes)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def fill_data(self):
        """Заполняет поля данными пользователя"""
        self.login_input.setText(self.user_data.get('login', ''))
        self.full_name_input.setText(self.user_data.get('full_name', ''))
        
        role = self.user_data.get('role_name', 'user')
        index = self.role_combo.findText(role)
        if index >= 0:
            self.role_combo.setCurrentIndex(index)
        
        self.active_checkbox.setChecked(self.user_data.get('is_active', 0) == 1)
    
    def save_changes(self):
        """Сохраняет изменения"""
        try:
            data = {
                'login': self.login_input.text().strip(),
                'full_name': self.full_name_input.text().strip(),
                'role': self.role_combo.currentText(),
                'is_active': 1 if self.active_checkbox.isChecked() else 0
            }
            
            success = DatabaseManager.update_user(self.user_data['user_id'], data)
            
            if success:
                QMessageBox.information(self, "Успешно", "Данные пользователя обновлены")
                self.accept()
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось обновить данные пользователя")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сохранения: {str(e)}")


class AddUserDialog(QDialog):
    """Диалог добавления нового пользователя"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Добавление пользователя")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.login_input = QLineEdit()
        form_layout.addRow("Логин *:", self.login_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Пароль *:", self.password_input)
        
        self.full_name_input = QLineEdit()
        form_layout.addRow("Полное имя:", self.full_name_input)
        
        self.email_input = QLineEdit()
        form_layout.addRow("Email:", self.email_input)
        
        self.role_combo = QComboBox()
        self.role_combo.addItems(["user", "admin", "manager"])
        form_layout.addRow("Роль:", self.role_combo)
        
        layout.addLayout(form_layout)
        
        note_label = QLabel("* - обязательные поля")
        note_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(note_label)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Добавить")
        save_btn.setStyleSheet("background-color: #27ae60; color: white;")
        save_btn.clicked.connect(self.add_user)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def add_user(self):
        """Добавляет нового пользователя"""
        login = self.login_input.text().strip()
        password = self.password_input.text().strip()
        
        if not login or not password:
            QMessageBox.warning(self, "Внимание", "Заполните все обязательные поля")
            return
        
        try:
            data = {
                'login': login,
                'password': password,
                'full_name': self.full_name_input.text().strip(),
                'email': self.email_input.text().strip(),
                'role': self.role_combo.currentText()
            }
            
            success = DatabaseManager.create_user(data)
            
            if success:
                QMessageBox.information(self, "Успешно", "Пользователь успешно добавлен")
                self.accept()
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось добавить пользователя")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка добавления: {str(e)}")