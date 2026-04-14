import sys
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTableWidget,
                             QTableWidgetItem, QHeaderView, QTabWidget,
                             QDateEdit, QGroupBox, QProgressBar, QScrollArea)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QIcon

from core.api_client import APIClient
from agent.styles import APP_STYLE


class ComputerDetailsDialog(QDialog):
    """Диалог с детальной информацией по компьютеру"""
    
    def __init__(self, computer_id, computer_data, parent=None):
        super().__init__(parent)
        self.computer_id = computer_id
        self.computer_data = computer_data
        self.api_client = APIClient()
        
        self.init_ui()
        self.load_all_data()
        
    def init_ui(self):
        self.setWindowTitle(f"PC-RMDS | Детали компьютера: {self.computer_data.get('hostname', 'Unknown')}")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(APP_STYLE)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        main_layout = QVBoxLayout(self)
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
        
        status_label = QLabel("Онлайн" if self.computer_data.get('is_online') else "Оффлайн")
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
        
        # Вкладка Общая информация
        self.tab_overview = QWidget()
        self.init_overview_tab()
        self.tabs.addTab(self.tab_overview, "📋 Общая информация")
        
        # Вкладка Метрики
        self.tab_metrics = QWidget()
        self.init_metrics_tab()
        self.tabs.addTab(self.tab_metrics, "📊 Метрики")
        
        # Вкладка Аномалии
        self.tab_anomalies = QWidget()
        self.init_anomalies_tab()
        self.tabs.addTab(self.tab_anomalies, "⚠️ Аномалии")
        
        # Вкладка Системные события
        self.tab_events = QWidget()
        self.init_events_tab()
        self.tabs.addTab(self.tab_events, "📝 События")
        
        # Вкладка Сессии
        self.tab_sessions = QWidget()
        self.init_sessions_tab()
        self.tabs.addTab(self.tab_sessions, "🕒 Сессии")
        
        # Вкладка IP адреса
        self.tab_ips = QWidget()
        self.init_ips_tab()
        self.tabs.addTab(self.tab_ips, "🌐 IP адреса")
        
        main_layout.addWidget(self.tabs)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("❌ Закрыть")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(120)
        btn_layout.addWidget(close_btn)
        
        main_layout.addLayout(btn_layout)
        
    def init_overview_tab(self):
        layout = QVBoxLayout(self.tab_overview)
        layout.setSpacing(15)
        
        # Статистические карточки
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        
        self.card_total_events = self.create_stat_card("📝", "Всего событий", "0", "#3498db")
        stats_layout.addWidget(self.card_total_events)
        
        self.card_anomalies = self.create_stat_card("⚠️", "Аномалий", "0", "#e74c3c")
        stats_layout.addWidget(self.card_anomalies)
        
        self.card_sessions = self.create_stat_card("🕒", "Сессий", "0", "#9b59b6")
        stats_layout.addWidget(self.card_sessions)
        
        self.card_uptime = self.create_stat_card("⏱️", "Время работы", "0 ч", "#2ecc71")
        stats_layout.addWidget(self.card_uptime)
        
        layout.addLayout(stats_layout)
        
        # Средние метрики
        metrics_group = QGroupBox("📊 Средние показатели за период")
        metrics_layout = QVBoxLayout(metrics_group)
        
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setMaximum(100)
        self.cpu_progress.setFormat("CPU: %p%")
        metrics_layout.addWidget(QLabel("Средняя загрузка CPU:"))
        metrics_layout.addWidget(self.cpu_progress)
        
        self.ram_progress = QProgressBar()
        self.ram_progress.setMaximum(100)
        self.ram_progress.setFormat("RAM: %p%")
        metrics_layout.addWidget(QLabel("Среднее использование RAM:"))
        metrics_layout.addWidget(self.ram_progress)
        
        self.disk_progress = QProgressBar()
        self.disk_progress.setMaximum(100)
        self.disk_progress.setFormat("Disk: %p%")
        metrics_layout.addWidget(QLabel("Среднее использование диска:"))
        metrics_layout.addWidget(self.disk_progress)
        
        layout.addWidget(metrics_group)
        
        # Информация о железе
        hw_group = QGroupBox("🔧 Конфигурация железа")
        hw_layout = QVBoxLayout(hw_group)
        self.hw_info_label = QLabel("Загрузка...")
        hw_layout.addWidget(self.hw_info_label)
        layout.addWidget(hw_group)
        
        layout.addStretch()
        
    def init_metrics_tab(self):
        layout = QVBoxLayout(self.tab_metrics)
        
        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(5)
        self.metrics_table.setHorizontalHeaderLabels(["Время", "CPU %", "RAM %", "Disk %", "Network KB/s"])
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.metrics_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.metrics_table)
        
    def init_anomalies_tab(self):
        layout = QVBoxLayout(self.tab_anomalies)
        
        self.anomalies_table = QTableWidget()
        self.anomalies_table.setColumnCount(4)
        self.anomalies_table.setHorizontalHeaderLabels(["Время", "CPU %", "RAM %", "Примечание"])
        self.anomalies_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.anomalies_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.anomalies_table)
        
    def init_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(3)
        self.events_table.setHorizontalHeaderLabels(["Время", "Тип", "Описание"])
        self.events_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.events_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.events_table)
        
    def init_sessions_tab(self):
        layout = QVBoxLayout(self.tab_sessions)
        
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(4)
        self.sessions_table.setHorizontalHeaderLabels(["Начало", "Конец", "Длительность", "IP адрес"])
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
        
    def create_stat_card(self, icon, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 10px;
                border-left: 4px solid {color};
                padding: 15px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(5)
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 24px;")
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color};")
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        
        card_layout.addWidget(icon_label)
        card_layout.addWidget(value_label)
        card_layout.addWidget(title_label)
        card_layout.addStretch()
        
        return card
        
    def get_period_params(self):
        return {
            'from': self.date_from.date().toString("yyyy-MM-dd"),
            'to': self.date_to.date().toString("yyyy-MM-dd"),
            'computer_id': self.computer_id
        }
        
    def load_all_data(self):
        params = self.get_period_params()
        
        # Загрузка средних метрик
        try:
            avg_metrics = self.api_client.get('/metrics/average', params)
            if avg_metrics and avg_metrics.get('success'):
                data = avg_metrics.get('data', {})
                self.cpu_progress.setValue(int(data.get('cpu_avg', 0)))
                self.ram_progress.setValue(int(data.get('ram_avg', 0)))
                self.disk_progress.setValue(int(data.get('disk_avg', 0)))
        except Exception as e:
            print(f"Ошибка загрузки средних метрик: {e}")
            
        # Загрузка статистики событий
        try:
            events_stats = self.api_client.get('/metrics/events/statistics', params)
            if events_stats and events_stats.get('success'):
                data = events_stats.get('data', {})
                self.card_total_events.findChild(QLabel, None, Qt.FindChildOption.FindDirectChildrenOnly)[1].setText(str(data.get('total', 0)))
        except Exception as e:
            print(f"Ошибка загрузки статистики событий: {e}")
            
        # Загрузка аномалий
        try:
            anomalies = self.api_client.get('/metrics/anomalies', params)
            if anomalies and anomalies.get('success'):
                data = anomalies.get('data', [])
                self.card_anomalies.findChild(QLabel, None, Qt.FindChildOption.FindDirectChildrenOnly)[1].setText(str(len(data)))
                self.fill_anomalies_table(data)
        except Exception as e:
            print(f"Ошибка загрузки аномалий: {e}")
            
        # Загрузка событий
        try:
            events = self.api_client.get('/metrics/events', params)
            if events and events.get('success'):
                self.fill_events_table(events.get('data', []))
        except Exception as e:
            print(f"Ошибка загрузки событий: {e}")
            
        # Загрузка метрик
        try:
            metrics = self.api_client.get('/metrics/performance', params)
            if metrics and metrics.get('success'):
                self.fill_metrics_table(metrics.get('data', []))
        except Exception as e:
            print(f"Ошибка загрузки метрик: {e}")
            
        # Загрузка сессий
        try:
            sessions = self.api_client.get(f'/computers/{self.computer_id}/sessions', {'limit': 100})
            if sessions and sessions.get('success'):
                data = sessions.get('data', [])
                self.card_sessions.findChild(QLabel, None, Qt.FindChildOption.FindDirectChildrenOnly)[1].setText(str(len(data)))
                self.fill_sessions_table(data)
        except Exception as e:
            print(f"Ошибка загрузки сессий: {e}")
            
        # Загрузка IP адресов
        try:
            ips = self.api_client.get(f'/computers/{self.computer_id}/ip-addresses')
            if ips and ips.get('success'):
                self.fill_ips_table(ips.get('data', []))
        except Exception as e:
            print(f"Ошибка загрузки IP адресов: {e}")
            
    def fill_anomalies_table(self, data):
        self.anomalies_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.anomalies_table.setItem(row, 0, QTableWidgetItem(str(item.get('timestamp', ''))))
            self.anomalies_table.setItem(row, 1, QTableWidgetItem(str(item.get('cpu_usage', ''))))
            self.anomalies_table.setItem(row, 2, QTableWidgetItem(str(item.get('ram_usage', ''))))
            self.anomalies_table.setItem(row, 3, QTableWidgetItem(str(item.get('note', ''))))
            
    def fill_events_table(self, data):
        self.events_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.events_table.setItem(row, 0, QTableWidgetItem(str(item.get('timestamp', ''))))
            self.events_table.setItem(row, 1, QTableWidgetItem(str(item.get('event_type', ''))))
            self.events_table.setItem(row, 2, QTableWidgetItem(str(item.get('message', ''))))
            
    def fill_metrics_table(self, data):
        self.metrics_table.setRowCount(min(len(data), 100))
        for row, item in enumerate(data[:100]):
            self.metrics_table.setItem(row, 0, QTableWidgetItem(str(item.get('timestamp', ''))))
            self.metrics_table.setItem(row, 1, QTableWidgetItem(str(item.get('cpu_usage', ''))))
            self.metrics_table.setItem(row, 2, QTableWidgetItem(str(item.get('ram_usage', ''))))
            self.metrics_table.setItem(row, 3, QTableWidgetItem(str(item.get('disk_usage', ''))))
            self.metrics_table.setItem(row, 4, QTableWidgetItem(str(item.get('network_speed', ''))))
            
    def fill_sessions_table(self, data):
        self.sessions_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.sessions_table.setItem(row, 0, QTableWidgetItem(str(item.get('start_time', ''))))
            self.sessions_table.setItem(row, 1, QTableWidgetItem(str(item.get('end_time', ''))))
            self.sessions_table.setItem(row, 2, QTableWidgetItem(str(item.get('duration', ''))))
            self.sessions_table.setItem(row, 3, QTableWidgetItem(str(item.get('ip_address', ''))))
            
    def fill_ips_table(self, data):
        self.ips_table.setRowCount(len(data))
        for row, item in enumerate(data):
            self.ips_table.setItem(row, 0, QTableWidgetItem(str(item.get('detected_at', ''))))
            self.ips_table.setItem(row, 1, QTableWidgetItem(str(item.get('ip_address', ''))))