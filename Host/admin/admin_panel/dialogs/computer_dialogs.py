import socket
from qtpy.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QFormLayout, QMessageBox)
from qtpy.QtCore import Qt

from core.api_client import APIClient as DatabaseManager
from core.hardware_id import HardwareIDGenerator


class EditComputerDialog(QDialog):
    """Диалог редактирования информации о компьютере"""
    
    def __init__(self, computer_data, parent=None):
        super().__init__(parent)
        self.computer_data = computer_data
        self.init_ui()
        self.fill_data()
    
    def init_ui(self):
        self.setWindowTitle("Редактирование компьютера")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.hostname_input = QLineEdit()
        form_layout.addRow("Hostname:", self.hostname_input)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["client", "admin"])
        form_layout.addRow("Тип компьютера:", self.type_combo)
        
        self.description_input = QLineEdit()
        form_layout.addRow("Описание:", self.description_input)
        
        self.location_input = QLineEdit()
        form_layout.addRow("Расположение:", self.location_input)
        
        self.department_input = QLineEdit()
        form_layout.addRow("Отдел:", self.department_input)
        
        self.inventory_input = QLineEdit()
        form_layout.addRow("Инвентарный номер:", self.inventory_input)
        
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
        """Заполняет поля данными компьютера"""
        self.hostname_input.setText(self.computer_data.get('hostname', ''))
        
        computer_type = self.computer_data.get('computer_type', 'client')
        index = self.type_combo.findText(computer_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        
        self.description_input.setText(self.computer_data.get('description', ''))
        self.location_input.setText(self.computer_data.get('location', ''))
        self.department_input.setText(self.computer_data.get('department', ''))
        self.inventory_input.setText(self.computer_data.get('inventory_number', ''))
    
    def save_changes(self):
        """Сохраняет изменения"""
        try:
            data = {
                'hostname': self.hostname_input.text().strip(),
                'computer_type': self.type_combo.currentText(),
                'description': self.description_input.text().strip(),
                'location': self.location_input.text().strip(),
                'department': self.department_input.text().strip(),
                'inventory_number': self.inventory_input.text().strip()
            }
            
            success = DatabaseManager.update_computer(self.computer_data['computer_id'], data)
            
            if success:
                QMessageBox.information(self, "Успешно", "Данные компьютера обновлены")
                self.accept()
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось обновить данные компьютера")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сохранения: {str(e)}")


class AddComputerDialog(QDialog):
    """Диалог добавления нового компьютера"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.users = []
        self.groups = []
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        self.setWindowTitle("Добавление компьютера")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.hostname_input = QLineEdit()
        self.hostname_input.setText(socket.gethostname())
        form_layout.addRow("Hostname *:", self.hostname_input)
        
        # MAC адрес определяется автоматически
        self.mac_address = HardwareIDGenerator.get_mac_address()
        mac_label = QLabel(self.mac_address)
        mac_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        form_layout.addRow("MAC адрес:", mac_label)
        
        # IP адрес определяется автоматически
        self.ip_address = self._get_ip_address()
        ip_label = QLabel(self.ip_address)
        ip_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        form_layout.addRow("IP адрес:", ip_label)
        
        # Выбор пользователя
        self.user_combo = QComboBox()
        self.user_combo.addItem("— Без пользователя —", None)
        form_layout.addRow("Пользователь:", self.user_combo)
        
        # Выбор группы
        self.group_combo = QComboBox()
        self.group_combo.addItem("— Без группы —", None)
        form_layout.addRow("Группа:", self.group_combo)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["client", "admin"])
        form_layout.addRow("Тип компьютера:", self.type_combo)
        
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
        save_btn.clicked.connect(self.add_computer)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _get_ip_address(self) -> str:
        """Получает текущий IP адрес"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"
    
    def load_data(self):
        """Загружает список пользователей и групп"""
        try:
            # Загружаем пользователей
            result = DatabaseManager.get('/users')
            if result and result.get('success'):
                users_data = result.get('data', [])
                if isinstance(users_data, list):
                    self.users = users_data
                elif isinstance(users_data, dict):
                    self.users = users_data.get('users', [])
                
                for user in self.users:
                    user_id = user.get('user_id')
                    login = user.get('login', f'ID {user_id}')
                    full_name = user.get('full_name', '')
                    display = f"{login} ({full_name})" if full_name else login
                    self.user_combo.addItem(display, user_id)
        except Exception as e:
            print(f"Ошибка загрузки пользователей: {e}")
        
        try:
            # Загружаем группы
            groups_result = DatabaseManager.get('/computers/groups')
            if groups_result and groups_result.get('success'):
                self.groups = groups_result.get('data', [])
                for group in self.groups:
                    group_id = group.get('group_id')
                    group_name = group.get('group_name', f'Группа {group_id}')
                    self.group_combo.addItem(group_name, group_id)
        except Exception as e:
            print(f"Ошибка загрузки групп: {e}")
    
    def add_computer(self):
        """Добавляет новый компьютер"""
        hostname = self.hostname_input.text().strip()
        
        if not hostname:
            QMessageBox.warning(self, "Внимание", "Введите Hostname")
            return
        
        try:
            data = {
                'hostname': hostname,
                'mac_address': self.mac_address,
                'ip_address': self.ip_address,
                'hardware_hash': f"manual_{self.mac_address}_{hostname}",
                'computer_type': self.type_combo.currentText()
            }
            
            # Пользователь
            user_id = self.user_combo.currentData()
            if user_id is not None:
                data['user_id'] = user_id
            
            # Группа
            group_id = self.group_combo.currentData()
            if group_id is not None:
                data['group_id'] = group_id
            
            # Отправляем запрос на сервер через POST /api/computers/register
            result = DatabaseManager.post('/computers/register', json=data)
            
            if result and result.get('success'):
                QMessageBox.information(self, "Успешно", "Компьютер успешно добавлен")
                self.accept()
            else:
                error_msg = result.get('error', 'Неизвестная ошибка') if result else 'Нет ответа от сервера'
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить компьютер: {error_msg}")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка добавления: {str(e)}")