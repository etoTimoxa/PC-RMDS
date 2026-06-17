"""
Окно уведомлений о критических событиях и аномалиях (колокольчик на панели админа)
"""
from datetime import datetime
from qtpy.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QScrollArea, QWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QMessageBox, QApplication)
from qtpy.QtCore import Qt, QTimer, QSize
from qtpy.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QBrush, QPen

from core.api_client import APIClient as DatabaseManager


class NotificationBadge(QLabel):
    """Виджет значка с количеством уведомлений"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #e74c3c;
                color: white;
                border-radius: 11px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self.hide()
    
    def update_count(self, count):
        if count > 0:
            self.setText(str(count) if count <= 99 else "99+")
            self.show()
        else:
            self.hide()


class NotificationsDialog(QDialog):
    """Диалог уведомлений о критических событиях и аномалиях"""
    
    def __init__(self, parent=None, parent_window=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.all_notifications = []
        self.setWindowTitle("🔔 Уведомления о событиях и аномалиях")
        self.setMinimumSize(800, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f6fa;
            }
        """)
        self.init_ui()
        self.load_notifications()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e74c3c, stop:1 #c0392b);
                border-radius: 10px;
                padding: 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        
        title_label = QLabel("🔔 Уведомления о критических событиях и аномалиях")
        title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        header_layout.addWidget(self.stats_label)
        
        layout.addWidget(header_frame)
        
        # Панель фильтрации
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
                padding: 8px;
            }
        """)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setSpacing(10)
        
        self.filter_all_btn = QPushButton("Все")
        self.filter_all_btn.setCheckable(True)
        self.filter_all_btn.setChecked(True)
        self.filter_all_btn.clicked.connect(lambda: self.apply_filter('all'))
        filter_layout.addWidget(self.filter_all_btn)
        
        self.filter_events_btn = QPushButton("🔴 События ОС")
        self.filter_events_btn.setCheckable(True)
        self.filter_events_btn.clicked.connect(lambda: self.apply_filter('critical_event'))
        filter_layout.addWidget(self.filter_events_btn)
        
        self.filter_anomalies_btn = QPushButton("📈 Аномалии")
        self.filter_anomalies_btn.setCheckable(True)
        self.filter_anomalies_btn.clicked.connect(lambda: self.apply_filter('anomaly_spike'))
        filter_layout.addWidget(self.filter_anomalies_btn)
        
        filter_layout.addStretch()
        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(32, 32)
        self.refresh_btn.setToolTip("Обновить уведомления")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.refresh_btn.clicked.connect(self.load_notifications)
        filter_layout.addWidget(self.refresh_btn)
        
        layout.addWidget(filter_frame)
        
        # Таблица уведомлений
        table_frame = QFrame()
        table_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
        """)
        table_layout = QVBoxLayout(table_frame)
        
        self.notifications_table = QTableWidget()
        self.notifications_table.setColumnCount(6)
        self.notifications_table.setHorizontalHeaderLabels([
            "🕐 Время", "💻 Компьютер", "👤 Пользователь",
            "📋 Тип", "📝 Описание", "⚠ Важность"
        ])
        
        header = self.notifications_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        
        self.notifications_table.setAlternatingRowColors(True)
        self.notifications_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.notifications_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.notifications_table.cellDoubleClicked.connect(self.on_notification_click)
        
        table_layout.addWidget(self.notifications_table)
        layout.addWidget(table_frame)
        
        # Нижняя панель
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
                padding: 8px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_frame)
        
        info_label = QLabel("💡 Двойной клик по уведомлению — открыть детали компьютера")
        info_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        bottom_layout.addWidget(info_label)
        
        bottom_layout.addStretch()
        
        close_btn = QPushButton("Закрыть")
        close_btn.setMinimumHeight(32)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        
        layout.addWidget(bottom_frame)
    
    def apply_filter(self, filter_type):
        """Применяет фильтр по типу уведомления"""
        self.filter_all_btn.setChecked(filter_type == 'all')
        self.filter_events_btn.setChecked(filter_type == 'critical_event')
        self.filter_anomalies_btn.setChecked(filter_type == 'anomaly_spike')
        
        self.current_filter = filter_type
        self.display_notifications()
    
    def load_notifications(self):
        """Загружает уведомления с сервера"""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳")
        
        try:
            data = DatabaseManager.get_recent_notifications(
                hours=2,
                cpu_threshold=85.0,
                ram_threshold=85.0,
                limit=100
            )
            
            if data:
                self.all_notifications = data.get('notifications', [])
                total = data.get('total', 0)
                critical_count = data.get('critical_count', 0)
                anomaly_count = data.get('anomaly_count', 0)
                event_count = data.get('event_count', 0)
                
                self.stats_label.setText(
                    f"Всего: {total} | 🔴 Событий: {event_count} | 📈 Аномалий: {anomaly_count} | "
                    f"⚠ Критических: {critical_count}"
                )
            else:
                self.all_notifications = []
                self.stats_label.setText("Нет данных")
            
            self.current_filter = getattr(self, 'current_filter', 'all')
            self.display_notifications()
            
        except Exception as e:
            print(f"[NOTIFICATIONS] Ошибка загрузки: {e}")
            self.all_notifications = []
            self.display_notifications()
        
        self.refresh_btn.setText("🔄")
        self.refresh_btn.setEnabled(True)
    
    def display_notifications(self):
        """Отображает уведомления в таблице"""
        filter_type = getattr(self, 'current_filter', 'all')
        
        if filter_type == 'all':
            filtered = self.all_notifications
        else:
            filtered = [n for n in self.all_notifications if n.get('type') == filter_type]
        
        self.notifications_table.setRowCount(len(filtered))
        
        for row, notif in enumerate(filtered):
            # Время
            timestamp = notif.get('timestamp', '')[:19]
            self.notifications_table.setItem(row, 0, QTableWidgetItem(timestamp))
            
            # Компьютер
            hostname = notif.get('hostname', 'Unknown')
            online = notif.get('is_online', 0)
            hostname_text = f"{'🟢' if online else '🔴'} {hostname}"
            host_item = QTableWidgetItem(hostname_text)
            host_item.setForeground(QColor("#27ae60" if online else "#e74c3c"))
            self.notifications_table.setItem(row, 1, host_item)
            
            # Пользователь
            user = notif.get('user_login', '—')
            self.notifications_table.setItem(row, 2, QTableWidgetItem(user))
            
            # Тип
            notif_type = notif.get('type', '')
            event_label = notif.get('event_label', '')
            if notif_type == 'critical_event':
                type_text = f"🔴 {event_label}"
            elif notif_type == 'anomaly_spike':
                type_text = f"📈 {event_label}"
            else:
                type_text = event_label
            
            type_item = QTableWidgetItem(type_text)
            if notif_type == 'critical_event':
                type_item.setForeground(QColor("#e74c3c"))
            elif notif_type == 'anomaly_spike':
                type_item.setForeground(QColor("#e67e22"))
            self.notifications_table.setItem(row, 3, type_item)
            
            # Описание
            description = notif.get('description', '')
            self.notifications_table.setItem(row, 4, QTableWidgetItem(description))
            
            # Важность
            severity = notif.get('severity', 'medium')
            if severity == 'critical':
                severity_text = "🔴 Критично"
                severity_color = QColor("#e74c3c")
            elif severity == 'high':
                severity_text = "🟠 Высокая"
                severity_color = QColor("#e67e22")
            else:
                severity_text = "🟡 Средняя"
                severity_color = QColor("#f39c12")
            
            sev_item = QTableWidgetItem(severity_text)
            sev_item.setForeground(severity_color)
            font = QFont()
            font.setBold(severity == 'critical')
            sev_item.setFont(font)
            self.notifications_table.setItem(row, 5, sev_item)
            
            # Сохраняем computer_id в первом столбце (UserRole)
            computer_id = notif.get('computer_id')
            if computer_id:
                self.notifications_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, computer_id)
                self.notifications_table.item(row, 0).setData(Qt.ItemDataRole.UserRole + 1, hostname)
    
    def on_notification_click(self, row, column):
        """Обработчик двойного клика по уведомлению"""
        # Получаем сохраненные данные
        item = self.notifications_table.item(row, 0)
        if not item:
            return
        
        computer_id = item.data(Qt.ItemDataRole.UserRole)
        hostname = item.data(Qt.ItemDataRole.UserRole + 1)
        
        if not computer_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера не найден")
            return
        
        self.accept()
        
        # Открываем окно деталей компьютера
        self._open_computer_details(computer_id, hostname)
    
    def _open_computer_details(self, computer_id, hostname):
        """Открывает окно деталей компьютера"""
        try:
            from admin.computer_details import ComputerDetailsWindow
            
            # Получаем данные компьютера
            computer_data = DatabaseManager.get_computer(computer_id)
            if not computer_data:
                computer_data = {'hostname': hostname, 'computer_id': computer_id}
            
            # Создаем окно
            details_window = ComputerDetailsWindow(
                hostname, computer_data,
                parent_window=self.parent_window
            )
            
            if self.parent_window:
                self.parent_window.hide()
            
            details_window.show()
            
        except Exception as e:
            print(f"[NOTIFICATIONS] Ошибка открытия деталей: {e}")
            QMessageBox.warning(
                None, "Ошибка",
                f"Не удалось открыть детали компьютера: {e}"
            )