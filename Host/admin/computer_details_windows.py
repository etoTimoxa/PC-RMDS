import sys
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTableWidget,
                             QTableWidgetItem, QHeaderView, QTabWidget,
                             QDateEdit, QGroupBox, QApplication)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QIcon, QPixmap, QColor

from core.api_client import APIClient
from .styles import get_main_window_stylesheet


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения"""
    from pathlib import Path
    
    # Пробуем PNG
    icon_path = Path(__file__).parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    # Пробуем ICO
    icon_path = Path(__file__).parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    # Пробуем в текущей директории
    icon_path = Path.cwd() / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    icon_path = Path.cwd() / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    # Создаем цветной квадрат
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(255, 140, 66))
    return QIcon(pixmap)


class ComputerDetailsWindow(QMainWindow):
    """Окно с детальной информацией по компьютеру"""
    
    def __init__(self, computer_id, computer_data):
        super().__init__()
        self.computer_id = computer_id
        self.computer_data = computer_data
        
        self.init_ui()
        self.load_all_data()
        
    def init_ui(self):
        self.setWindowTitle(f"PC-RMDS | Детали компьютера: {self.computer_data.get('hostname', 'Unknown')}")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(get_main_window_stylesheet())
        self.setWindowIcon(get_app_icon())
        self.showMaximized()
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #3498db;
                border-radius: 10px;
                padding: 15px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel(f"🖥️ {self.computer_data.get('hostname', 'Unknown')}")
        title_label.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        
        status_label = QLabel("🟢 Онлайн" if self.computer_data.get('is_online') else "🔴 Оффлайн")
        status_label.setStyleSheet(f"color: {'#2ecc71' if self.computer_data.get('is_online') else '#e74c3c'}; font-size: 14px; font-weight: bold;")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(status_label)
        
        main_layout.addWidget(header_frame)
        
        # Выбор периода
        period_layout = QHBoxLayout()
        period_layout.addWidget(QLabel("Период:"))
        
        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addDays(-7))
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        period_layout.addWidget(self.date_from)
        
        period_layout.addWidget(QLabel("по"))
        
        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        period_layout.addWidget(self.date_to)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.load_all_data)
        period_layout.addWidget(refresh_btn)
        period_layout.addStretch()
        
        main_layout.addLayout(period_layout)
        
        # Табы
        self.tabs = QTabWidget()
        
        self.tab_overview = QWidget()
        self.init_overview_tab()
        self.tabs.addTab(self.tab_overview, "📋 Общая информация")
        
        self.tab_metrics = QWidget()
        self.init_metrics_tab()
        self.tabs.addTab(self.tab_metrics, "📊 Метрики")
        
        self.tab_events = QWidget()
        self.init_events_tab()
        self.tabs.addTab(self.tab_events, "📝 События")
        
        self.tab_sessions = QWidget()
        self.init_sessions_tab()
        self.tabs.addTab(self.tab_sessions, "🕒 Сессии")
        
        self.tab_ips = QWidget()
        self.init_ips_tab()
        self.tabs.addTab(self.tab_ips, "🌐 IP адреса")
        
        main_layout.addWidget(self.tabs)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        back_btn = QPushButton("← Назад к списку")
        back_btn.clicked.connect(self.go_back)
        back_btn.setMinimumWidth(150)
        btn_layout.addWidget(back_btn)
        
        close_btn = QPushButton("❌ Закрыть")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(120)
        btn_layout.addWidget(close_btn)
        
        main_layout.addLayout(btn_layout)
        
    def init_overview_tab(self):
        layout = QVBoxLayout(self.tab_overview)
        layout.setSpacing(15)
        
        # Информация о компьютере
        info_group = QGroupBox("💻 Информация о компьютере")
        info_layout = QVBoxLayout(info_group)
        
        self.computer_info_label = QLabel("Загрузка...")
        self.computer_info_label.setWordWrap(True)
        info_layout.addWidget(self.computer_info_label)
        
        layout.addWidget(info_group)
        
        # Информация о железе
        hw_group = QGroupBox("🔧 Конфигурация железа")
        hw_layout = QVBoxLayout(hw_group)
        
        self.hw_info_label = QLabel("Загрузка...")
        self.hw_info_label.setWordWrap(True)
        hw_layout.addWidget(self.hw_info_label)
        
        layout.addWidget(hw_group)
        
        layout.addStretch()
        
    def init_metrics_tab(self):
        layout = QVBoxLayout(self.tab_metrics)
        
        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(5)
        self.metrics_table.setHorizontalHeaderLabels(["Время", "CPU %", "RAM %", "Disk %", "Network MB/s"])
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.metrics_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.metrics_table)
        
    def init_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(4)
        self.events_table.setHorizontalHeaderLabels(["Время", "Тип", "Уровень", "Описание"])
        self.events_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.events_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.events_table)
        
    def init_sessions_tab(self):
        layout = QVBoxLayout(self.tab_sessions)
        
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(4)
        self.sessions_table.setHorizontalHeaderLabels(["Начало", "Конец", "Статус", "Длительность"])
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sessions_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.sessions_table)
        
    def init_ips_tab(self):
        layout = QVBoxLayout(self.tab_ips)
        
        self.ips_table = QTableWidget()
        self.ips_table.setColumnCount(2)
        self.ips_table.setHorizontalHeaderLabels(["Дата обнаружения", "IP адрес"])
        self.ips_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ips_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.ips_table)
        
    def get_period_params(self):
        return {
            'from': self.date_from.date().toString("yyyy-MM-dd"),
            'to': self.date_to.date().toString("yyyy-MM-dd")
        }
        
    def load_all_data(self):
        params = self.get_period_params()
        
        # Загрузка информации о компьютере
        try:
            computer = APIClient.get_computer(self.computer_id)
            if computer:
                info_text = f"""
                <b>ID:</b> {computer.get('computer_id')}<br>
                <b>Hostname:</b> {computer.get('hostname')}<br>
                <b>MAC Address:</b> {computer.get('mac_address')}<br>
                <b>Тип:</b> {computer.get('computer_type')}<br>
                <b>ОС:</b> {computer.get('os_name', 'Unknown')} {computer.get('os_version', '')}<br>
                <b>Последний вход:</b> {computer.get('last_online')}<br>
                <b>Создан:</b> {computer.get('created_at')}
                """
                self.computer_info_label.setText(info_text)
                
                hw_text = f"""
                <b>CPU:</b> {computer.get('cpu_model', 'Unknown')}<br>
                <b>Ядра:</b> {computer.get('cpu_cores', 'N/A')}<br>
                <b>RAM:</b> {computer.get('ram_total', 'N/A')} GB<br>
                <b>Диск:</b> {computer.get('storage_total', 'N/A')} GB<br>
                <b>GPU:</b> {computer.get('gpu_model', 'Unknown')}<br>
                <b>Материнская плата:</b> {computer.get('motherboard', 'Unknown')}<br>
                <b>BIOS:</b> {computer.get('bios_version', 'Unknown')}
                """
                self.hw_info_label.setText(hw_text)
        except Exception as e:
            print(f"Ошибка загрузки информации о компьютере: {e}")
        
        # Загрузка метрик производительности
        try:
            result = APIClient.get('/metrics/performance', params={'computer_id': self.computer_id, **params})
            if result and result.get('success'):
                data = result.get('data', {})
                metrics = data.get('performance', data.get('metrics', []))
                if isinstance(metrics, list):
                    self.fill_metrics_table(metrics[:100])
        except Exception as e:
            print(f"Ошибка загрузки метрик: {e}")
        
        # Загрузка событий
        try:
            result = APIClient.get('/metrics/events', params={'computer_id': self.computer_id, **params})
            if result and result.get('success'):
                data = result.get('data', {})
                events = data.get('events', [])
                if isinstance(events, list):
                    self.fill_events_table(events[:100])
        except Exception as e:
            print(f"Ошибка загрузки событий: {e}")
        
        # Загрузка сессий
        try:
            result = APIClient.get_computer_sessions(self.computer_id, limit=50)
            if result:
                self.fill_sessions_table(result)
        except Exception as e:
            print(f"Ошибка загрузки сессий: {e}")
        
        # Загрузка IP адресов
        try:
            result = APIClient.get_computer_ip_addresses(self.computer_id)
            if result:
                self.fill_ips_table(result)
        except Exception as e:
            print(f"Ошибка загрузки IP адресов: {e}")
        
    def fill_metrics_table(self, data):
        self.metrics_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.metrics_table.setItem(row, 0, QTableWidgetItem(str(item.get('timestamp', ''))[:19]))
            self.metrics_table.setItem(row, 1, QTableWidgetItem(str(item.get('cpu_usage', ''))))
            self.metrics_table.setItem(row, 2, QTableWidgetItem(str(item.get('ram_usage', ''))))
            self.metrics_table.setItem(row, 3, QTableWidgetItem(str(item.get('disk_usage', ''))))
            self.metrics_table.setItem(row, 4, QTableWidgetItem(str(item.get('network_speed', ''))))
            
    def fill_events_table(self, data):
        self.events_table.setRowCount(len(data))
        for row, item in enumerate(data):
            event_data = item.get('data', item)
            self.events_table.setItem(row, 0, QTableWidgetItem(str(item.get('timestamp', ''))[:19]))
            self.events_table.setItem(row, 1, QTableWidgetItem(str(event_data.get('event_type', item.get('type', '')))))
            self.events_table.setItem(row, 2, QTableWidgetItem(str(event_data.get('severity', 'info'))))
            self.events_table.setItem(row, 3, QTableWidgetItem(str(event_data.get('message', ''))[:200]))
            
    def fill_sessions_table(self, data):
        self.sessions_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.sessions_table.setItem(row, 0, QTableWidgetItem(str(item.get('start_time', ''))[:19]))
            end_time = str(item.get('end_time', ''))[:19] if item.get('end_time') else 'Активна'
            self.sessions_table.setItem(row, 1, QTableWidgetItem(end_time))
            self.sessions_table.setItem(row, 2, QTableWidgetItem(str(item.get('status_name', 'active'))))
            
            duration = ""
            if item.get('start_time'):
                try:
                    start = datetime.fromisoformat(str(item.get('start_time')).replace('Z', '+00:00'))
                    end = datetime.fromisoformat(str(item.get('end_time')).replace('Z', '+00:00')) if item.get('end_time') else datetime.now()
                    delta = end - start
                    hours = delta.total_seconds() // 3600
                    minutes = (delta.total_seconds() % 3600) // 60
                    duration = f"{int(hours)}ч {int(minutes)}м"
                except:
                    pass
            self.sessions_table.setItem(row, 3, QTableWidgetItem(duration))
            
    def fill_ips_table(self, data):
        """Заполняет таблицу IP адресов"""
        self.ips_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.ips_table.setItem(row, 0, QTableWidgetItem(str(item.get('detected_at', ''))[:19]))
            self.ips_table.setItem(row, 1, QTableWidgetItem(str(item.get('ip_address', ''))))
            
    def go_back(self):
        """Возврат к панели администратора"""
        from .admin_panel import AdminPanelWindow
        self.admin_panel = AdminPanelWindow(self.computer_data)
        self.admin_panel.show()
        self.close()
        
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        from .admin_panel import AdminPanelWindow
        self.admin_panel = AdminPanelWindow(self.computer_data)
        self.admin_panel.show()
        event.accept()
