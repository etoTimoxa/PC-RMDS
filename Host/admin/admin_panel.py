import socket
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QFrame, QTableWidget,
                            QTableWidgetItem, QHeaderView, QSystemTrayIcon,
                            QMenu, QStatusBar, QMessageBox, QApplication)
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
        self.init_ui()
        self.setup_tray()
        
        # Таймер обновления данных
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(30000)  # Каждые 30 секунд
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle(f"PC-RMDS | Администратор: {self.computer_data.get('login', 'Unknown')}")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(get_main_window_stylesheet())
        self.showMaximized()
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # === Заголовок ===
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #3498db;
                border-radius: 10px;
                padding: 15px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel("🖥️ ПАНЕЛЬ АДМИНИСТРАТОРА")
        title_label.setStyleSheet("""
            color: white;
            font-size: 20px;
            font-weight: bold;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        
        main_layout.addWidget(header_frame)
        
        # === Карточки статистики ===
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        
        self.card_total = self.create_stat_card("🖥️", "Всего компьютеров", "0", "#3498db")
        self.card_online = self.create_stat_card("🟢", "Онлайн", "0", "#2ecc71")
        self.card_offline = self.create_stat_card("🔴", "Оффлайн", "0", "#e74c3c")
        self.card_sessions = self.create_stat_card("🕒", "Активных сессий", "0", "#9b59b6")
        
        stats_layout.addWidget(self.card_total)
        stats_layout.addWidget(self.card_online)
        stats_layout.addWidget(self.card_offline)
        stats_layout.addWidget(self.card_sessions)
        
        main_layout.addLayout(stats_layout)
        
        # === Таблица компьютеров ===
        table_frame = QFrame()
        table_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #ddd;
            }
        """)
        table_layout = QVBoxLayout(table_frame)
        
        table_title = QLabel("📋 Подключенные компьютеры")
        table_title.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
            padding: 10px;
        """)
        table_layout.addWidget(table_title)
        
        self.computers_table = QTableWidget()
        self.computers_table.setColumnCount(6)
        self.computers_table.setHorizontalHeaderLabels([
            "ID", "Hostname", "IP адрес", "Тип", "Статус", "Последний вход"
        ])
        
        # Настройка таблицы
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
        
        main_layout.addWidget(table_frame)
        
        # === Кнопки управления ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.setMinimumHeight(40)
        refresh_btn.setMinimumWidth(120)
        refresh_btn.clicked.connect(self.refresh_data)
        btn_layout.addWidget(refresh_btn)
        
        settings_btn = QPushButton("⚙️ Настройки")
        settings_btn.setMinimumHeight(40)
        settings_btn.setMinimumWidth(120)
        settings_btn.clicked.connect(self.open_settings)
        btn_layout.addWidget(settings_btn)
        
        logout_btn = QPushButton("🚪 Выйти")
        logout_btn.setMinimumHeight(40)
        logout_btn.setMinimumWidth(120)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        logout_btn.clicked.connect(self.logout)
        btn_layout.addWidget(logout_btn)
        
        main_layout.addLayout(btn_layout)
        
        # === Статус бар ===
        self.statusBar().showMessage(f"Администратор: {self.computer_data.get('login', 'Unknown')} | PC-RMDS Agent")
        
        # Загружаем данные
        self.refresh_data()
    
    def create_stat_card(self, icon, title, value, color):
        """Создает карточку статистики"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 10px;
                border-left: 4px solid {color};
                padding: 10px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(3)
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 20px;")
        
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        value_label.setStyleSheet(f"""
            QLabel#statValue {{
                font-size: 24px;
                font-weight: bold;
                color: {color};
            }}
        """)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        
        card_layout.addWidget(icon_label)
        card_layout.addWidget(value_label)
        card_layout.addWidget(title_label)
        
        # Сохраняем ссылки на виджеты для обновления
        card.value_label = value_label
        
        return card
    
    def get_ip_address(self):
        """Получает IP адрес"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"
    
    def refresh_data(self):
        """Обновляет данные таблицы"""
        try:
            # Получаем список компьютеров через API
            result = DatabaseManager.get_computers()
            
            computers = []
            if result and isinstance(result, dict):
                # Если результат - словарь с ключом computers
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
            
            # Обновляем таблицу
            self.computers_table.setRowCount(len(computers))
            
            online_count = 0
            offline_count = 0
            
            for row, comp in enumerate(computers):
                if not isinstance(comp, dict):
                    continue
                
                computer_id = comp.get('computer_id', '')
                hostname = comp.get('hostname', 'Unknown')
                
                # Получаем IP адрес
                ip_address = comp.get('current_ip', comp.get('ip_address', comp.get('ip', 'Unknown')))
                
                computer_type = comp.get('computer_type', 'client')
                
                is_online = comp.get('is_online', 0) == 1
                if is_online:
                    online_count += 1
                else:
                    offline_count += 1
                
                status_text = "🟢 Онлайн" if is_online else "🔴 Офлайн"
                status_item = QTableWidgetItem(status_text)
                
                last_online = comp.get('last_online', 'N/A')
                if last_online and isinstance(last_online, str):
                    last_online = last_online[:19]  # Обрезаем до читаемого формата
                
                self.computers_table.setItem(row, 0, QTableWidgetItem(str(computer_id)))
                self.computers_table.setItem(row, 1, QTableWidgetItem(str(hostname)))
                self.computers_table.setItem(row, 2, QTableWidgetItem(str(ip_address)))
                self.computers_table.setItem(row, 3, QTableWidgetItem(str(computer_type)))
                self.computers_table.setItem(row, 4, status_item)
                self.computers_table.setItem(row, 5, QTableWidgetItem(str(last_online)))
            
            # Обновляем карточки статистики
            total_count = len(computers)
            self.card_total.value_label.setText(str(total_count))
            self.card_online.value_label.setText(str(online_count))
            self.card_offline.value_label.setText(str(offline_count))
            
            # Получаем активные сессии
            try:
                sessions_result = DatabaseManager.get('/sessions/active')
                if sessions_result and sessions_result.get('success'):
                    sessions_data = sessions_result.get('data', {})
                    active_sessions = sessions_data.get('count', 0)
                    self.card_sessions.value_label.setText(str(active_sessions))
            except Exception as e:
                print(f"Ошибка получения сессий: {e}")
            
            self.statusBar().showMessage(f"Обновлено: {datetime.now().strftime('%H:%M:%S')} | Онлайн: {online_count}, Оффлайн: {offline_count}")
            
        except Exception as e:
            print(f"Ошибка обновления данных: {e}")
            import traceback
            traceback.print_exc()
    
    def setup_tray(self):
        """Настраивает системный трей"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("PC-RMDS | Администратор")
        
        # Контекстное меню
        tray_menu = QMenu()
        
        show_action = QAction("📺 Показать", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        settings_action = QAction("⚙️ Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        
        quit_action = QAction("🚪 Выйти", self)
        quit_action.triggered.connect(self.logout)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
    
    def on_tray_activated(self, reason):
        """Обработка клика по трею"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
    
    def open_settings(self):
        """Открывает настройки"""
        from agent.settings_dialog import SettingsDialog
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec()
            
    def open_computer_details(self, row, column):
        """Открывает окно с детальной информацией по компьютеру"""
        computer_id_item = self.computers_table.item(row, 0)
        if not computer_id_item:
            return
            
        try:
            computer_id = int(computer_id_item.text())
            hostname_item = self.computers_table.item(row, 1)
            
            computer_data = {
                'computer_id': computer_id,
                'hostname': hostname_item.text() if hostname_item else 'Unknown',
                'is_online': self.computers_table.item(row, 4).text() == "🟢 Онлайн"
            }
            
            # Исправлено: используем ComputerDetailsWindow
            from .computer_details_windows import ComputerDetailsWindow
            self.details_window = ComputerDetailsWindow(computer_id, computer_data)
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
            # Отключаем автоматическую авторизацию
            settings = QSettings("RemoteAccess", "Agent")
            settings.setValue("auto_auth", False)
            settings.sync()
            
            self.close()
            if self.tray_icon:
                self.tray_icon.hide()
            QApplication.quit()
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        # Сворачиваем в трей вместо закрытия
        event.ignore()
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "PC-RMDS Agent",
                "Приложение свернуто в трей",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )