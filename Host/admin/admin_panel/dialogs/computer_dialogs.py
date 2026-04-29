from qtpy.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QFormLayout, QMessageBox)
from qtpy.QtCore import Qt

from core.api_client import APIClient as DatabaseManager


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
        self.type_combo.addItems(["client", "laptop", "server", "admin"])
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
        self.init_ui()
    
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
        form_layout.addRow("Hostname *:", self.hostname_input)
        
        self.hardware_hash_input = QLineEdit()
        form_layout.addRow("Hardware Hash *:", self.hardware_hash_input)
        
        self.mac_input = QLineEdit()
        form_layout.addRow("MAC адрес *:", self.mac_input)
        
        self.user_id_input = QLineEdit()
        form_layout.addRow("ID пользователя:", self.user_id_input)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["client", "laptop", "server", "admin"])
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
    
    def add_computer(self):
        """Добавляет новый компьютер"""
        hostname = self.hostname_input.text().strip()
        hardware_hash = self.hardware_hash_input.text().strip()
        mac_address = self.mac_input.text().strip()
        
        if not hostname or not hardware_hash or not mac_address:
            QMessageBox.warning(self, "Внимание", "Заполните все обязательные поля")
            return
        
        try:
            data = {
                'hostname': hostname,
                'hardware_hash': hardware_hash,
                'mac_address': mac_address,
                'computer_type': self.type_combo.currentText()
            }
            
            user_id = self.user_id_input.text().strip()
            if user_id:
                data['user_id'] = int(user_id)
            
            success = DatabaseManager.register_computer(data)
            
            if success:
                QMessageBox.information(self, "Успешно", "Компьютер успешно добавлен")
                self.accept()
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось добавить компьютер")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка добавления: {str(e)}")