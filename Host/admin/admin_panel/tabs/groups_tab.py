"""Вкладка "Группы" - управление группами компьютеров"""

from datetime import datetime
from qtpy.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLineEdit, QDialog,
                             QFormLayout, QMessageBox, QTextEdit)
from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QColor

from core.api_client import APIClient as DatabaseManager


class AddEditGroupDialog(QDialog):
    """Диалог добавления/редактирования группы"""

    def __init__(self, parent=None, group_data=None):
        super().__init__(parent)
        self.group_data = group_data
        self.is_edit = group_data is not None
        self.init_ui()
        if self.is_edit:
            self.fill_data()

    def init_ui(self):
        title = "Редактирование группы" if self.is_edit else "Добавление группы"
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Название группы")
        form_layout.addRow("Название *:", self.name_input)

        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(80)
        self.desc_input.setPlaceholderText("Описание группы (необязательно)")
        form_layout.addRow("Описание:", self.desc_input)

        layout.addLayout(form_layout)

        note_label = QLabel("* - обязательные поля")
        note_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(note_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Сохранить" if self.is_edit else "Добавить")
        save_btn.setStyleSheet("background-color: #27ae60; color: white;")
        save_btn.clicked.connect(self.save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def fill_data(self):
        self.name_input.setText(self.group_data.get('group_name', ''))
        self.desc_input.setText(self.group_data.get('description', ''))

    def save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Внимание", "Введите название группы")
            return

        description = self.desc_input.toPlainText().strip()

        try:
            if self.is_edit:
                group_id = self.group_data['group_id']
                success = DatabaseManager.update_computer_group(group_id, name, description)
                if success:
                    QMessageBox.information(self, "Успешно", "Группа обновлена")
                    self.accept()
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось обновить группу")
            else:
                group_id = DatabaseManager.create_computer_group(name, description)
                if group_id:
                    QMessageBox.information(self, "Успешно", "Группа добавлена")
                    self.accept()
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось добавить группу")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {str(e)}")


class GroupsTab(QWidget):
    """Вкладка со списком групп компьютеров"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.all_groups = []
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
        self.search_input.setPlaceholderText("Название группы...")
        self.search_input.setMinimumWidth(200)
        self.search_input.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_input)

        filter_layout.addStretch()

        add_btn = QPushButton("Добавить группу")
        add_btn.setMinimumHeight(35)
        add_btn.clicked.connect(self.add_group)
        filter_layout.addWidget(add_btn)

        delete_btn = QPushButton("Удалить")
        delete_btn.setMinimumHeight(35)
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        delete_btn.clicked.connect(self.delete_selected_group)
        filter_layout.addWidget(delete_btn)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.setMinimumHeight(35)
        refresh_btn.clicked.connect(self.refresh_data)
        filter_layout.addWidget(refresh_btn)

        layout.addWidget(filter_frame)

        # Таблица групп
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
        table_title = QLabel("Группы компьютеров")
        table_title.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            padding: 12px;
        """)
        table_header_layout.addWidget(table_title)

        self.groups_count_label = QLabel("")
        self.groups_count_label.setStyleSheet("color: #7f8c8d; padding: 12px;")
        table_header_layout.addWidget(self.groups_count_label)
        table_header_layout.addStretch()

        table_layout.addLayout(table_header_layout)

        self.groups_table = QTableWidget()
        self.groups_table.setColumnCount(4)
        self.groups_table.setHorizontalHeaderLabels([
            "ID", "Название", "Компьютеров", "Описание"
        ])

        header = self.groups_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.groups_table.setAlternatingRowColors(True)
        self.groups_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.groups_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.groups_table.itemDoubleClicked.connect(self.edit_selected_group)

        table_layout.addWidget(self.groups_table)

        layout.addWidget(table_frame)

    def apply_filters(self):
        search_text = self.search_input.text().lower()

        filtered = []
        for group in self.all_groups:
            if search_text:
                name = group.get('group_name', '').lower()
                desc = group.get('description', '').lower()
                if search_text not in name and search_text not in desc:
                    continue
            filtered.append(group)

        self.update_table_display(filtered)
        self.groups_count_label.setText(f"Показано: {len(filtered)} из {len(self.all_groups)}")

    def update_table_display(self, groups):
        self.groups_table.setRowCount(len(groups))

        for row, group in enumerate(groups):
            if not isinstance(group, dict):
                continue

            group_id = group.get('group_id', 'N/A')
            group_name = group.get('group_name', 'Без названия')
            computer_count = group.get('computer_count', 0)
            description = group.get('description', '')

            self.groups_table.setItem(row, 0, QTableWidgetItem(str(group_id)))
            self.groups_table.setItem(row, 1, QTableWidgetItem(str(group_name)))
            self.groups_table.setItem(row, 2, QTableWidgetItem(str(computer_count)))
            self.groups_table.setItem(row, 3, QTableWidgetItem(str(description) if description else "—"))

    def refresh_data(self):
        try:
            result = DatabaseManager.get('/computers/groups')
            if result and result.get('success'):
                groups = result.get('data', [])
                self.all_groups = groups if isinstance(groups, list) else []
            else:
                self.all_groups = []
            self.apply_filters()
        except Exception as e:
            print(f"Ошибка загрузки групп: {e}")
            self.all_groups = []
            self.groups_table.setRowCount(0)

    def add_group(self):
        dialog = AddEditGroupDialog(self)
        if dialog.exec():
            self.refresh_data()

    def edit_selected_group(self):
        selected = self.groups_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Внимание", "Выберите группу для редактирования")
            return

        row = selected[0].row()
        group_id_item = self.groups_table.item(row, 0)
        if not group_id_item:
            return

        try:
            group_id = int(group_id_item.text())
            group_data = next((g for g in self.all_groups if g.get('group_id') == group_id), None)
            if group_data:
                dialog = AddEditGroupDialog(self, group_data)
                if dialog.exec():
                    self.refresh_data()
        except Exception as e:
            print(f"Ошибка редактирования группы: {e}")

    def delete_selected_group(self):
        selected = self.groups_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Внимание", "Выберите группу для удаления")
            return

        row = selected[0].row()
        group_id_item = self.groups_table.item(row, 0)
        name_item = self.groups_table.item(row, 1)
        if not group_id_item or not name_item:
            return

        group_id = int(group_id_item.text())
        group_name = name_item.text()

        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены что хотите удалить группу '{group_name}'?\n\n"
            "Компьютеры в этой группе будут отвязаны от неё.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = DatabaseManager.delete(f'/computers/groups/{group_id}')
                if result and result.get('success'):
                    QMessageBox.information(self, "Успешно", f"Группа '{group_name}' удалена")
                    self.refresh_data()
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось удалить группу")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка удаления: {str(e)}")