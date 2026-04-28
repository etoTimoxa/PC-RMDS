from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLineEdit, QComboBox, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.api_client import APIClient as DatabaseManager
from ..dialogs.user_dialogs import EditUserDialog, AddUserDialog


class UsersTab(QWidget):
    """Вкладка со списком пользователей"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.all_users = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Панель действий
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
        self.search_input.setPlaceholderText("Логин, имя, email...")
        self.search_input.setMinimumWidth(200)
        self.search_input.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_input)
        
        filter_layout.addStretch()
        
        add_btn = QPushButton("➕ Добавить пользователя")
        add_btn.setMinimumHeight(35)
        add_btn.clicked.connect(self.add_user)
        filter_layout.addWidget(add_btn)
        
        
        reset_pass_btn = QPushButton("🔑 Сброс пароля")
        reset_pass_btn.setMinimumHeight(35)
        reset_pass_btn.clicked.connect(self.reset_user_password)
        filter_layout.addWidget(reset_pass_btn)
        
        self.block_btn = QPushButton("🔒 Блокировать / Разблокировать")
        self.block_btn.setMinimumHeight(35)
        self.block_btn.setStyleSheet("background-color: #f39c12; color: white;")
        self.block_btn.clicked.connect(self.toggle_block_user)
        filter_layout.addWidget(self.block_btn)

        delete_btn = QPushButton("🗑️ Удалить")
        delete_btn.setMinimumHeight(35)
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        delete_btn.clicked.connect(self.delete_selected_user)
        filter_layout.addWidget(delete_btn)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.setMinimumHeight(35)
        refresh_btn.clicked.connect(self.refresh_data)
        filter_layout.addWidget(refresh_btn)
        
        layout.addWidget(filter_frame)
        
        # Таблица пользователей
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
        table_title = QLabel("Список пользователей")
        table_title.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            padding: 12px;
        """)
        table_header_layout.addWidget(table_title)
        
        self.users_count_label = QLabel("")
        self.users_count_label.setStyleSheet("color: #7f8c8d; padding: 12px;")
        table_header_layout.addWidget(self.users_count_label)
        table_header_layout.addStretch()
        
        table_layout.addLayout(table_header_layout)
        
        self.users_table = QTableWidget()
        self.users_table.setColumnCount(7)
        self.users_table.setHorizontalHeaderLabels([
            "ID", "Логин", "Полное имя", "Email", "Роль", "Активен", "Последний вход"
        ])
        
        header = self.users_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        
        self.users_table.setAlternatingRowColors(True)
        self.users_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.users_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Двойной клик для редактирования
        self.users_table.itemDoubleClicked.connect(self.edit_user_by_double_click)
        
        # Обработчик изменения выбора для обновления кнопки блокировки
        self.users_table.itemSelectionChanged.connect(self.update_block_button_text)
        
        table_layout.addWidget(self.users_table)
        
        layout.addWidget(table_frame)
    
    def apply_filters(self):
        """Применяет фильтры к таблице"""
        search_text = self.search_input.text().lower()
        
        filtered = []
        for user in self.all_users:
            if search_text:
                login = user.get('login', '').lower()
                full_name = user.get('full_name', '').lower()
                email = user.get('email', '').lower()
                if search_text not in login and search_text not in full_name and search_text not in email:
                    continue
            
            filtered.append(user)
        
        self.update_table_display(filtered)
        self.users_count_label.setText(f"Показано: {len(filtered)} из {len(self.all_users)}")
    
    def update_table_display(self, users):
        """Обновляет отображение таблицы"""
        self.users_table.setRowCount(len(users))
        
        for row, user in enumerate(users):
            if not isinstance(user, dict):
                continue
            
            user_id = user.get('user_id', 'N/A')
            login = user.get('login', 'Unknown')
            full_name = user.get('full_name', '')
            email = user.get('email', '')
            role_name = user.get('role_name', 'user')
            
            is_active = user.get('is_active', 0) == 1
            active_text = "Да" if is_active else "Нет"
            active_color = "#27ae60" if is_active else "#e74c3c"
            active_item = QTableWidgetItem(active_text)
            active_item.setForeground(QColor(active_color))
            
            last_login = user.get('last_login', 'Никогда')
            if last_login and isinstance(last_login, str):
                last_login = last_login[:19]
            
            self.users_table.setItem(row, 0, QTableWidgetItem(str(user_id)))
            self.users_table.setItem(row, 1, QTableWidgetItem(str(login)))
            self.users_table.setItem(row, 2, QTableWidgetItem(str(full_name)))
            self.users_table.setItem(row, 3, QTableWidgetItem(str(email)))
            self.users_table.setItem(row, 4, QTableWidgetItem(str(role_name)))
            self.users_table.setItem(row, 5, active_item)
            self.users_table.setItem(row, 6, QTableWidgetItem(str(last_login)))
    
    def refresh_data(self):
        """Обновляет данные таблицы"""
        try:
            result = DatabaseManager.get_users()
            
            users = []
            if result and isinstance(result, dict):
                if 'users' in result:
                    users = result['users']
                elif 'data' in result:
                    data = result['data']
                    if isinstance(data, list):
                        users = data
            elif isinstance(result, list):
                users = result
            
            self.all_users = users
            self.apply_filters()
            
        except Exception as e:
            print(f"Ошибка обновления данных пользователей: {e}")
    
    def add_user(self):
        """Открывает диалог добавления нового пользователя"""
        dialog = AddUserDialog(self)
        if dialog.exec():
            self.refresh_data()
    
    def edit_user_by_double_click(self, item):
        """Открывает редактирование пользователя по двойному клику"""
        row = item.row()
        user_id_item = self.users_table.item(row, 0)
        if not user_id_item:
            return
        
        try:
            user_id = int(user_id_item.text())
            user_data = next((u for u in self.all_users if u.get('user_id') == user_id), None)
            
            if user_data:
                dialog = EditUserDialog(user_data, self)
                if dialog.exec():
                    self.refresh_data()
        
        except Exception as e:
            print(f"Ошибка редактирования пользователя: {e}")
    
    def update_block_button_text(self):
        """Обновляет текст кнопки блокировки в зависимости от статуса выбранного пользователя"""
        selected_rows = self.users_table.selectedItems()
        if not selected_rows:
            self.block_btn.setText("🔒 Блокировать / Разблокировать")
            return
        
        row = selected_rows[0].row()
        active_item = self.users_table.item(row, 5)
        
        if active_item and active_item.text() == "Да":
            self.block_btn.setText("🔒 Заблокировать")
        else:
            self.block_btn.setText("🔓 Разблокировать")
    
    def reset_user_password(self):
        """Сбрасывает пароль пользователя"""
        selected_rows = self.users_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите пользователя для сброса пароля")
            return
        
        row = selected_rows[0].row()
        user_id_item = self.users_table.item(row, 0)
        login_item = self.users_table.item(row, 1)
        if not user_id_item or not login_item:
            return
        
        user_id = int(user_id_item.text())
        login = login_item.text()
        
        reply = QMessageBox.question(
            self,
            "Сброс пароля",
            f"Вы уверены что хотите сбросить пароль для пользователя '{login}'?\n\nПользователю будет необходимо сменить пароль при следующем входе.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = DatabaseManager.post(f"/users/{user_id}/reset-password")
                if success and success.get('success'):
                    QMessageBox.information(self, "Успешно", f"Пароль для пользователя '{login}' сброшен. При следующем входе пользователь должен будет сменить пароль.")
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось сбросить пароль")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка сброса пароля: {str(e)}")
    
    def toggle_block_user(self):
        """Блокирует/разблокирует выбранного пользователя"""
        selected_rows = self.users_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите пользователя")
            return
        
        row = selected_rows[0].row()
        user_id_item = self.users_table.item(row, 0)
        login_item = self.users_table.item(row, 1)
        active_item = self.users_table.item(row, 5)
        
        if not user_id_item or not login_item or not active_item:
            return
        
        user_id = int(user_id_item.text())
        login = login_item.text()
        is_active = active_item.text() == "Да"
        
        new_status = 0 if is_active else 1
        action_text = "заблокировать" if is_active else "разблокировать"
        
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Вы уверены что хотите {action_text} пользователя '{login}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Отдельный эндпоинт для блокировки пользователя
                success = DatabaseManager.post(f'/users/{user_id}/block', json={'is_active': new_status})
                
                if success and success.get('success'):
                    if new_status == 0:
                        QMessageBox.information(self, "Успешно", f"Пользователь '{login}' заблокирован")
                    else:
                        QMessageBox.information(self, "Успешно", f"Пользователь '{login}' разблокирован")
                    self.refresh_data()
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось изменить статус пользователя")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка блокировки: {str(e)}")
    
    def delete_selected_user(self):
        """Удаляет выбранного пользователя"""
        selected_rows = self.users_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите пользователя для удаления")
            return
        
        row = selected_rows[0].row()
        user_id_item = self.users_table.item(row, 0)
        login_item = self.users_table.item(row, 1)
        if not user_id_item or not login_item:
            return
        
        user_id = int(user_id_item.text())
        login = login_item.text()
        
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены что хотите удалить пользователя '{login}'?\n\nЭто действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = DatabaseManager.delete_user(user_id)
                if success:
                    QMessageBox.information(self, "Успешно", f"Пользователь '{login}' удален")
                    self.refresh_data()
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось удалить пользователя")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка удаления: {str(e)}")
