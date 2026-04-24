from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLineEdit, QComboBox, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.api_client import APIClient as DatabaseManager
from ..dialogs.computer_dialogs import EditComputerDialog, AddComputerDialog
from ...computer_details import ComputerDetailsWindow


class ComputersTab(QWidget):
    """Вкладка со списком компьютеров"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.all_computers = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Панель фильтрации и действий
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
                padding: 10px;
            }
        """)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setSpacing(15)
        
        filter_layout.addWidget(QLabel("Поиск:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Hostname, IP, пользователь...")
        self.search_input.setMinimumWidth(200)
        self.search_input.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_input)
        
        filter_layout.addWidget(QLabel("Статус:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Все", "Онлайн", "Офлайн"])
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.status_filter)
        
        filter_layout.addWidget(QLabel("Тип:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["Все", "admin", "client"])
        self.type_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.type_filter)
        
        filter_layout.addStretch()
        
        # Кнопки действий
        add_btn = QPushButton("➕ Добавить компьютер")
        add_btn.setMinimumHeight(35)
        add_btn.clicked.connect(self.add_computer)
        filter_layout.addWidget(add_btn)
        
        
        delete_btn = QPushButton("🗑️ Удалить")
        delete_btn.setMinimumHeight(35)
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        delete_btn.clicked.connect(self.delete_selected_computer)
        filter_layout.addWidget(delete_btn)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.setMinimumHeight(35)
        refresh_btn.clicked.connect(self.refresh_data)
        filter_layout.addWidget(refresh_btn)
        
        layout.addWidget(filter_frame)
        
        # Таблица компьютеров
        table_frame = QFrame()
        table_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        table_layout = QVBoxLayout(table_frame)
        
        table_header_layout = QHBoxLayout()
        table_title = QLabel("Список компьютеров")
        table_title.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            padding: 12px;
        """)
        table_header_layout.addWidget(table_title)
        
        self.computers_count_label = QLabel("")
        self.computers_count_label.setStyleSheet("color: #7f8c8d; padding: 12px;")
        table_header_layout.addWidget(self.computers_count_label)
        table_header_layout.addStretch()
        
        table_layout.addLayout(table_header_layout)
        
        self.computers_table = QTableWidget()
        self.computers_table.setColumnCount(6)
        self.computers_table.setHorizontalHeaderLabels([
            "ID", "Hostname", "IP адрес", "Пользователь", "Статус", "Последний вход"
        ])
        
        header = self.computers_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        
        self.computers_table.setAlternatingRowColors(True)
        self.computers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.computers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.computers_table.cellDoubleClicked.connect(self.open_computer_details)
        
        table_layout.addWidget(self.computers_table)
        
        layout.addWidget(table_frame)
    
    def apply_filters(self):
        """Применяет фильтры к таблице"""
        search_text = self.search_input.text().lower()
        status = self.status_filter.currentText()
        comp_type = self.type_filter.currentText()
        
        filtered = []
        for comp in self.all_computers:
            if search_text:
                hostname = comp.get('hostname', '').lower()
                ip = comp.get('ip_address', comp.get('current_ip', '')).lower()
                user = comp.get('login', comp.get('user_login', '')).lower()
                if search_text not in hostname and search_text not in ip and search_text not in user:
                    continue
            
            is_online = comp.get('is_online', 0) == 1
            if status == "Онлайн" and not is_online:
                continue
            if status == "Офлайн" and is_online:
                continue
            
            if comp_type != "Все":
                comp_type_val = comp.get('computer_type', 'client')
                if comp_type_val != comp_type:
                    continue
            
            filtered.append(comp)
        
        self.update_table_display(filtered)
        self.computers_count_label.setText(f"Показано: {len(filtered)} из {len(self.all_computers)}")
    
    def update_table_display(self, computers):
        """Обновляет отображение таблицы"""
        self.computers_table.setRowCount(len(computers))
        
        online_count = 0
        offline_count = 0
        
        for row, comp in enumerate(computers):
            if not isinstance(comp, dict):
                continue
            
            computer_id = comp.get('computer_id', 'N/A')
            hostname = comp.get('hostname', 'Unknown')
            ip_address = comp.get('ip_address', comp.get('current_ip', 'Unknown'))
            user_login = comp.get('login', comp.get('user_login', 'Не назначен'))
            
            is_online = comp.get('is_online', 0) == 1
            if is_online:
                online_count += 1
            else:
                offline_count += 1
            
            status_text = "Онлайн" if is_online else "Офлайн"
            status_color = "#27ae60" if is_online else "#e74c3c"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            
            last_online = comp.get('last_online', 'N/A')
            if last_online and isinstance(last_online, str):
                last_online = last_online[:19]
            
            self.computers_table.setItem(row, 0, QTableWidgetItem(str(computer_id)))
            self.computers_table.setItem(row, 1, QTableWidgetItem(str(hostname)))
            self.computers_table.setItem(row, 2, QTableWidgetItem(str(ip_address)))
            self.computers_table.setItem(row, 3, QTableWidgetItem(str(user_login)))
            self.computers_table.setItem(row, 4, status_item)
            self.computers_table.setItem(row, 5, QTableWidgetItem(str(last_online)))
        
        if self.parent_window:
            self.parent_window.statusBar().showMessage(f"Онлайн: {online_count}, Офлайн: {offline_count} | {datetime.now().strftime('%H:%M:%S')}")
    
    def refresh_data(self):
        """Обновляет данные таблицы"""
        try:
            result = DatabaseManager.get_computers()
            
            computers = []
            if result and isinstance(result, dict):
                if 'computers' in result:
                    computers = result['computers']
                elif 'data' in result:
                    data = result['data']
                    if isinstance(data, dict) and 'computers' in data:
                        computers = data['computers']
                    elif isinstance(data, list):
                        computers = data
            elif isinstance(result, list):
                computers = result
            
            if not computers:
                print("Нет данных о компьютерах")
                self.computers_table.setRowCount(0)
                return
            
            self.all_computers = computers
            self.apply_filters()
            
        except Exception as e:
            print(f"Ошибка обновления данных компьютеров: {e}")
    
    def open_computer_details(self, row, column):
        """Открывает окно с детальной информацией по компьютеру"""
        computer_id_item = self.computers_table.item(row, 0)
        hostname_item = self.computers_table.item(row, 1)
        if not hostname_item or not computer_id_item:
            return
        
        try:
            computer_id = int(computer_id_item.text())
            hostname = hostname_item.text()
            
            # Найдем полные данные компьютера
            computer_data = next((c for c in self.all_computers if c.get('computer_id') == computer_id), None)
            
            if computer_data:
                self.details_window = ComputerDetailsWindow(hostname, computer_data, parent_window=self.parent_window)
                self.parent_window.hide()
                self.details_window.show()
            
        except Exception as e:
            print(f"Ошибка открытия деталей компьютера: {e}")
    
    def add_computer(self):
        """Открывает диалог добавления нового компьютера"""
        dialog = AddComputerDialog(self)
        if dialog.exec():
            self.refresh_data()
    
    def edit_selected_computer(self):
        """Редактирует выбранный компьютер"""
        selected_rows = self.computers_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите компьютер для редактирования")
            return
        
        row = selected_rows[0].row()
        computer_id_item = self.computers_table.item(row, 0)
        if not computer_id_item:
            return
        
        try:
            computer_id = int(computer_id_item.text())
            computer_data = next((c for c in self.all_computers if c.get('computer_id') == computer_id), None)
            
            if computer_data:
                dialog = EditComputerDialog(computer_data, self)
                if dialog.exec():
                    self.refresh_data()
        
        except Exception as e:
            print(f"Ошибка редактирования компьютера: {e}")
    
    def delete_selected_computer(self):
        """Удаляет выбранный компьютер"""
        selected_rows = self.computers_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите компьютер для удаления")
            return
        
        row = selected_rows[0].row()
        computer_id_item = self.computers_table.item(row, 0)
        hostname_item = self.computers_table.item(row, 1)
        if not computer_id_item or not hostname_item:
            return
        
        computer_id = int(computer_id_item.text())
        hostname = hostname_item.text()
        
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены что хотите удалить компьютер '{hostname}'?\n\nЭто действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = DatabaseManager.delete_computer(computer_id)
                if success:
                    QMessageBox.information(self, "Успешно", f"Компьютер '{hostname}' удален")
                    self.refresh_data()
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось удалить компьютер")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка удаления: {str(e)}")