"""Диалоговые окна"""

import sys
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                            QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton,
                            QDialogButtonBox, QGroupBox, QCalendarWidget, QMessageBox,
                            QFileDialog)
from PyQt6.QtCore import Qt, QDate

from core.api_client import APIClient
from .widgets import get_app_icon


class EditComputerDialog(QDialog):
    """Диалог для редактирования информации о компьютере"""
    
    def __init__(self, computer_data, computer_id, parent=None):
        super().__init__(parent)
        self.computer_data = computer_data
        self.computer_id = computer_id
        self.groups = []
        self.update_data = {}
        self.init_ui()
        self.load_groups()
    
    def init_ui(self):
        self.setWindowTitle("Редактирование компьютера")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.hostname_edit = QLineEdit()
        self.hostname_edit.setText(self.computer_data.get('hostname', ''))
        form_layout.addRow("Hostname:", self.hostname_edit)
        
        self.description_edit = QTextEdit()
        self.description_edit.setText(self.computer_data.get('description', ''))
        self.description_edit.setMaximumHeight(80)
        form_layout.addRow("Описание:", self.description_edit)
        
        self.group_combo = QComboBox()
        self.group_combo.addItem("— Без группы —", None)
        form_layout.addRow("Группа:", self.group_combo)
        
        self.inventory_edit = QLineEdit()
        self.inventory_edit.setText(self.computer_data.get('inventory_number', ''))
        form_layout.addRow("Инв. номер:", self.inventory_edit)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["client", "admin"])
        current_type = self.computer_data.get('computer_type', 'client')
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        form_layout.addRow("Тип:", self.type_combo)
        
        layout.addLayout(form_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def load_groups(self):
        try:
            result = APIClient.get('/computers/groups')
            if result and result.get('success'):
                self.groups = result.get('data', [])
                current_group_id = self.computer_data.get('group_id')
                
                for group in self.groups:
                    self.group_combo.addItem(group['group_name'], group['group_id'])
                    if current_group_id == group['group_id']:
                        self.group_combo.setCurrentIndex(self.group_combo.count() - 1)
        except Exception as e:
            print(f"Ошибка загрузки групп: {e}")
    
    def save(self):
        data = {}
        
        if self.hostname_edit.text() != self.computer_data.get('hostname', ''):
            data['hostname'] = self.hostname_edit.text()
        
        if self.description_edit.toPlainText() != self.computer_data.get('description', ''):
            data['description'] = self.description_edit.toPlainText()
        
        group_id = self.group_combo.currentData()
        if group_id != self.computer_data.get('group_id'):
            data['group_id'] = group_id
        
        if self.inventory_edit.text() != self.computer_data.get('inventory_number', ''):
            data['inventory_number'] = self.inventory_edit.text()
        
        if self.type_combo.currentText() != self.computer_data.get('computer_type', 'client'):
            data['computer_type'] = self.type_combo.currentText()
        
        if data:
            self.update_data = data
            self.accept()
        else:
            self.reject()
    
    def get_update_data(self):
        return self.update_data


class EditSessionDialog(QDialog):
    """Диалог для просмотра информации о сессии"""
    
    def __init__(self, session_data, computer_id=None, parent=None):
        super().__init__(parent)
        self.session_data = session_data
        self.computer_id = computer_id or session_data.get('computer_id')
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle(f"Информация о сессии #{self.session_data.get('session_id', '')}")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        info_group = QGroupBox("Детали сессии")
        info_layout = QFormLayout(info_group)
        
        info_layout.addRow("ID сессии:", QLabel(str(self.session_data.get('session_id', '—'))))
        info_layout.addRow("Компьютер ID:", QLabel(str(self.session_data.get('computer_id', '—'))))
        
        token = self.session_data.get('session_token', '—')
        token_display = token[:50] + "..." if len(token) > 50 else token
        info_layout.addRow("Токен:", QLabel(token_display))
        info_layout.addRow("Статус:", QLabel(self.session_data.get('status_name', '—')))
        
        start_time = self.session_data.get('start_time', '')
        if start_time:
            info_layout.addRow("Начало:", QLabel(str(start_time)[:19]))
        
        end_time = self.session_data.get('end_time')
        if end_time:
            info_layout.addRow("Окончание:", QLabel(str(end_time)[:19]))
        else:
            info_layout.addRow("Окончание:", QLabel("Активна"))
        
        last_activity = self.session_data.get('last_activity', '')
        if last_activity:
            info_layout.addRow("Последняя активность:", QLabel(str(last_activity)[:19]))
        
        info_layout.addRow("Отправлено JSON:", QLabel(str(self.session_data.get('json_sent_count', 0))))
        info_layout.addRow("Ошибок:", QLabel(str(self.session_data.get('error_count', 0))))
        
        layout.addWidget(info_group)
        
        if self.session_data.get('status_name') == 'active' or self.session_data.get('status_id') == 1:
            close_btn = QPushButton("Завершить сессию")
            close_btn.setStyleSheet("background-color: #e74c3c;")
            close_btn.clicked.connect(self.close_session)
            layout.addWidget(close_btn)
        
        close_dialog_btn = QPushButton("Закрыть")
        close_dialog_btn.clicked.connect(self.accept)
        layout.addWidget(close_dialog_btn)
    
    def close_session(self):
        computer_id = self.computer_id or self.session_data.get('computer_id')
        session_id = self.session_data.get('session_id')
        
        if not computer_id or not session_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера или сессии не определен")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Вы уверены, что хотите завершить сессию #{session_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Используем правильный метод close_session_by_id
                result = APIClient.close_session_by_id(session_id)
                if result:
                    QMessageBox.information(self, "Успех", f"Сессия #{session_id} успешно завершена")
                    self.accept()
                else:
                    QMessageBox.warning(self, "Ошибка", "Не удалось завершить сессию")
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Ошибка: {str(e)}")


class DateRangeDialog(QDialog):
    """Диалог для выбора диапазона дат с двумя календарями"""
    
    def __init__(self, parent=None, start_date=None, end_date=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор периода")
        self.setModal(True)
        self.setMinimumSize(650, 450)
        
        layout = QVBoxLayout(self)
        
        title = QLabel("Выберите диапазон дат")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ff8c42; padding: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        calendar_layout = QHBoxLayout()
        calendar_layout.setSpacing(20)
        
        from_group = QGroupBox("Дата начала")
        from_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ff8c42;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ff8c42;
            }
        """)
        from_layout = QVBoxLayout(from_group)
        self.from_calendar = QCalendarWidget()
        self.from_calendar.setGridVisible(True)
        if start_date:
            self.from_calendar.setSelectedDate(start_date)
        from_layout.addWidget(self.from_calendar)
        calendar_layout.addWidget(from_group)
        
        to_group = QGroupBox("Дата окончания")
        to_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ff8c42;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ff8c42;
            }
        """)
        to_layout = QVBoxLayout(to_group)
        self.to_calendar = QCalendarWidget()
        self.to_calendar.setGridVisible(True)
        if end_date:
            self.to_calendar.setSelectedDate(end_date)
        to_layout.addWidget(self.to_calendar)
        calendar_layout.addWidget(to_group)
        
        layout.addLayout(calendar_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_dates(self):
        return self.from_calendar.selectedDate(), self.to_calendar.selectedDate()