import socket
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QFrame, QTableWidget,
                            QTableWidgetItem, QHeaderView, QSystemTrayIcon,
                            QMenu, QStatusBar, QMessageBox, QApplication,
                            QLineEdit, QComboBox)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QIcon, QAction, QPixmap, QColor

from core.api_client import APIClient as DatabaseManager
from utils.platform_utils import get_config_dir
from .styles import get_main_window_stylesheet


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения"""
    from pathlib import Path
    icon_path = Path(__file__).parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    icon_path = Path(__file__).parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(52, 152, 219))
    return QIcon(pixmap)


class AdminPanelWindow(QMainWindow):
    """Окно панели администратора"""
    
    def __init__(self, computer_data, parent=None):
        super().__init__(parent)
        self.computer_data = computer_data
        self.tray_icon = None
        self.all_computers = []
        self.init_ui()
        self.setup_tray()
        
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(30000)
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle(f"PC-RMDS | Администратор: {self.computer_data.get('login', 'Unknown')}")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(get_main_window_stylesheet())
        self.showMaximized()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff8c42, stop:1 #e67e22);
                border-radius: 12px;
                padding: 15px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel("PC-RMDS • ПАНЕЛЬ АДМИНИСТРАТОРА")
        title_label.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        
        main_layout.addWidget(header_frame)
        
        # Панель фильтрации
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
        
        refresh_btn = QPushButton("Обновить")
        refresh_btn.setMinimumHeight(35)
        refresh_btn.setMinimumWidth(100)
        refresh_btn.clicked.connect(self.refresh_data)
        filter_layout.addWidget(refresh_btn)
        
        main_layout.addWidget(filter_frame)
        
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
        table_title = QLabel("Подключенные компьютеры")
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
        self.computers_table.setColumnCount(5)
        self.computers_table.setHorizontalHeaderLabels([
            "Hostname", "IP адрес", "Пользователь", "Статус", "Последний вход"
        ])
        
        header = self.computers_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        
        self.computers_table.setAlternatingRowColors(True)
        self.computers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.computers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.computers_table.cellDoubleClicked.connect(self.open_computer_details)
        
        table_layout.addWidget(self.computers_table)
        
        main_layout.addWidget(table_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        logout_btn = QPushButton("Выйти")
        logout_btn.setMinimumHeight(40)
        logout_btn.setMinimumWidth(140)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        logout_btn.clicked.connect(self.logout)
        btn_layout.addWidget(logout_btn)
        
        main_layout.addLayout(btn_layout)
        
        self.statusBar().showMessage(f"Администратор: {self.computer_data.get('login', 'Unknown')} | PC-RMDS")
        
        self.refresh_data()
    
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
            
            hostname = comp.get('hostname', 'Unknown')
            ip_address = comp.get('ip_address', comp.get('current_ip', 'Unknown'))
            
            user_login = comp.get('login', comp.get('user_login', 'Не назначен'))
            if user_login == 'Не назначен' or not user_login:
                user_login = 'Не назначен'
            
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
            
            self.computers_table.setItem(row, 0, QTableWidgetItem(str(hostname)))
            self.computers_table.setItem(row, 1, QTableWidgetItem(str(ip_address)))
            self.computers_table.setItem(row, 2, QTableWidgetItem(str(user_login)))
            self.computers_table.setItem(row, 3, status_item)
            self.computers_table.setItem(row, 4, QTableWidgetItem(str(last_online)))
        
        self.statusBar().showMessage(f"Онлайн: {online_count}, Офлайн: {offline_count} | {datetime.now().strftime('%H:%M:%S')}")
    
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
            print(f"Ошибка обновления данных: {e}")
            import traceback
            traceback.print_exc()
    
    def setup_tray(self):
        """Настраивает системный трей"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("PC-RMDS | Администратор")
        
        tray_menu = QMenu()
        
        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Выйти", self)
        quit_action.triggered.connect(self.logout)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
    
    def on_tray_activated(self, reason):
        """Обработка клика по трею"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
    
    def open_computer_details(self, row, column):
        """Открывает окно с детальной информацией по компьютеру"""
        hostname_item = self.computers_table.item(row, 0)
        if not hostname_item:
            return
            
        try:
            hostname = hostname_item.text()
            ip_item = self.computers_table.item(row, 1)
            user_item = self.computers_table.item(row, 2)
            status_item = self.computers_table.item(row, 3)
            
            computer_data = {
                'hostname': hostname,
                'ip_address': ip_item.text() if ip_item else 'Unknown',
                'user_login': user_item.text() if user_item else 'Не назначен',
                'is_online': status_item.text() == "Онлайн" if status_item else False
            }
            
            from .computer_details_windows import ComputerDetailsWindow
            self.details_window = ComputerDetailsWindow(hostname, computer_data)
            self.hide()
            self.details_window.show()
            
        except Exception as e:
            print(f"Ошибка открытия деталей компьютера: {e}")
    
    def logout(self):
        """Выход из системы"""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите выйти?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            settings = QSettings("RemoteAccess", "Agent")
            settings.setValue("auto_auth", False)
            settings.sync()
            
            self.close()
            if self.tray_icon:
                self.tray_icon.hide()
            QApplication.quit()
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        event.ignore()
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "PC-RMDS",
                "Приложение свернуто в трей",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )