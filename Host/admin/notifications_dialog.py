"""
Всплывающая шторка уведомлений о критических событиях и аномалиях
"""
from datetime import datetime
from qtpy.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QWidget, QMessageBox,
                             QApplication, QLineEdit, QComboBox)
from qtpy.QtCore import Qt, QTimer, QPoint, QSettings
from qtpy.QtGui import QColor, QFont

from core.api_client import APIClient as DatabaseManager


class NotificationBadge(QLabel):
    """Виджет значка с количеством непрочитанных уведомлений на колокольчике"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #e74c3c;
                color: white;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }
        """)
        self.hide()
    
    def update_count(self, count):
        if count > 0:
            self.setText(str(count) if count <= 99 else "99+")
            self.show()
        else:
            self.hide()


class NotificationItem(QFrame):
    """Один элемент уведомления в шторке"""
    
    def __init__(self, notif_data, parent=None):
        super().__init__(parent)
        self.notif_data = notif_data
        self.computer_id = notif_data.get('computer_id')
        self.hostname = notif_data.get('hostname', 'Unknown')
        self.setup_ui()
    
    def setup_ui(self):
        severity = self.notif_data.get('severity', 'medium')
        notif_type = self.notif_data.get('type', '')
        event_label = self.notif_data.get('event_label', '')
        description = self.notif_data.get('description', '')
        timestamp = self.notif_data.get('timestamp', '')[:19]
        computer = self.notif_data.get('hostname', 'Unknown')
        
        if severity == 'critical':
            bg_color = '#fdedec'
            border_color = '#e74c3c'
        elif severity == 'high':
            bg_color = '#fef5e7'
            border_color = '#e67e22'
        else:
            bg_color = '#fef9e7'
            border_color = '#f39c12'
        
        self.setStyleSheet(f"""
            NotificationItem {{
                background-color: {bg_color};
                border-left: 4px solid {border_color};
                border-radius: 6px;
                margin: 3px 8px;
                padding: 6px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(8, 6, 8, 6)
        
        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)
        
        type_icon = "🔴" if notif_type == 'critical_event' else "📈"
        
        computer_label = QLabel(f"{type_icon} {computer}")
        computer_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50; border: none;")
        top_layout.addWidget(computer_label)
        
        top_layout.addStretch()
        
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("font-size: 10px; color: #95a5a6; border: none;")
        top_layout.addWidget(time_label)
        
        layout.addLayout(top_layout)
        
        type_label = QLabel(event_label)
        type_label.setStyleSheet("font-size: 11px; color: #34495e; border: none;")
        layout.addWidget(type_label)
        
        if description and description != event_label:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("font-size: 10px; color: #7f8c8d; border: none;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def mousePressEvent(self, event):
        if self.computer_id:
            parent_widget = self.parentWidget()
            while parent_widget and not hasattr(parent_widget, '_on_notification_item_clicked'):
                parent_widget = parent_widget.parentWidget()
            
            if parent_widget and hasattr(parent_widget, '_on_notification_item_clicked'):
                parent_widget._on_notification_item_clicked(self.computer_id, self.hostname)
        
        super().mousePressEvent(event)


class NotificationsPopover(QFrame):
    """Всплывающая шторка с уведомлениями"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.all_notifications = []
        self._computer_filter = ''
        self._last_all = 0  # сколько всего было до отметки "прочитано"
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        self.setFixedWidth(440)
        self.setMaximumHeight(520)
        
        self.init_ui()
    
    def init_ui(self):
        main_frame = QFrame(self)
        main_frame.setObjectName("popoverMain")
        main_frame.setStyleSheet("""
            QFrame#popoverMain {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #dcdde1;
            }
        """)
        main_layout = QVBoxLayout(main_frame)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Заголовок
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e74c3c, stop:1 #c0392b);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                padding: 8px 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)
        
        title_label = QLabel("🔔 Уведомления")
        title_label.setStyleSheet("color: white; font-size: 13px; font-weight: bold; border: none;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 10px; border: none;")
        header_layout.addWidget(self.stats_label)
        
        main_layout.addWidget(header_frame)
        
        # Фильтры
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                padding: 6px 10px;
                border-bottom: 1px solid #ecf0f1;
            }
        """)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 5, 10, 5)
        filter_layout.setSpacing(6)
        
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍 Фильтр по компьютеру...")
        self.filter_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                background: white;
            }
        """)
        self.filter_input.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.filter_input, 1)
        
        self.type_filter = QComboBox()
        self.type_filter.addItems(["Все", "🔴 События", "📈 Аномалии"])
        self.type_filter.setStyleSheet("""
            QComboBox {
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                background: white;
            }
        """)
        self.type_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.type_filter)
        
        main_layout.addWidget(filter_frame)
        
        # Область прокрутки
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #bdc3c7;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(2)
        self.content_layout.setContentsMargins(0, 5, 0, 5)
        self.content_layout.addStretch()
        
        scroll.setWidget(self.content_widget)
        main_layout.addWidget(scroll, 1)
        
        # Нижняя панель
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                border-top: 1px solid #ecf0f1;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(10, 6, 10, 6)
        
        self.mark_read_btn = QPushButton("✓ Прочитано")
        self.mark_read_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #219a52; }
        """)
        self.mark_read_btn.clicked.connect(self.mark_all_read)
        bottom_layout.addWidget(self.mark_read_btn)
        
        bottom_layout.addStretch()
        
        info_label = QLabel("💡 Нажмите на уведомление")
        info_label.setStyleSheet("color: #95a5a6; font-size: 10px; border: none;")
        bottom_layout.addWidget(info_label)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #bdc3c7;
                color: white;
                border: none;
                border-radius: 11px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #95a5a6; }
        """)
        close_btn.clicked.connect(self.hide_popover)
        bottom_layout.addWidget(close_btn)
        
        main_layout.addWidget(bottom_frame)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.addWidget(main_frame)
    
    def apply_filters(self):
        self._computer_filter = self.filter_input.text().strip().lower()
        self.display_notifications()
    
    def get_filtered_notifications(self):
        filtered = self.all_notifications
        
        type_text = self.type_filter.currentText()
        if type_text == "🔴 События":
            filtered = [n for n in filtered if n.get('type') == 'critical_event']
        elif type_text == "📈 Аномалии":
            filtered = [n for n in filtered if n.get('type') == 'anomaly_spike']
        
        if self._computer_filter:
            filtered = [
                n for n in filtered
                if self._computer_filter in n.get('hostname', '').lower()
            ]
        
        return filtered
    
    def show_popover(self, button_pos, button_height=34):
        pos = self.parentWidget().mapToGlobal(
            QPoint(button_pos.x() - self.width() + 60, button_pos.y() + button_height + 5)
        )
        self.move(pos)
        self.show()
    
    def show_popover_global(self, global_pos):
        x = global_pos.x() - self.width() + 60
        y = global_pos.y() + 5
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            if x + self.width() > screen_rect.right():
                x = screen_rect.right() - self.width() - 10
            if x < screen_rect.left():
                x = screen_rect.left() + 10
        self.move(x, y)
        self.show()
    
    def hide_popover(self):
        self.hide()
    
    def mark_all_read(self):
        """Помечает все уведомления как прочитанные (только в текущем сеансе)"""
        # Просто очищаем список и скрываем бейдж
        # Не сохраняем timestamp, чтобы при следующей загрузке уведомления снова появились
        parent = self.parent()
        if parent and hasattr(parent, 'notif_badge'):
            parent.notif_badge.hide()
            parent.notifications_btn.setToolTip("🔔 Нет новых уведомлений")
        
        self.all_notifications = []
        self.display_notifications()
    
    def load_notifications(self):
        """Загружает уведомления из облачного хранилища за последние 24 часа"""
        try:
            # Очищаем старый кэш read_until_time, который мог блокировать уведомления
            settings = QSettings("PC-RMDS", "Notifications")
            if settings.contains("read_until_time"):
                settings.remove("read_until_time")
                settings.sync()
            
            data = DatabaseManager.get_recent_notifications(
                hours=24,
                cpu_threshold=85.0,
                ram_threshold=85.0,
                limit=100
            )
            
            if data:
                all_items = data.get('notifications', [])
                
                # Показываем все уведомления за последние 24 часа
                self.all_notifications = all_items
                
                anomaly_count = sum(1 for n in self.all_notifications if n.get('type') == 'anomaly_spike')
                event_count = sum(1 for n in self.all_notifications if n.get('type') == 'critical_event')
                self.stats_label.setText(f"{len(self.all_notifications)} | 🔴{event_count} 📈{anomaly_count}")
                
                # Обновляем бейдж
                parent = self.parent()
                if parent and hasattr(parent, 'notif_badge'):
                    new_count = len(self.all_notifications)
                    parent.notif_badge.update_count(new_count)
                    parent.notifications_btn.setToolTip(
                        f"🔔 {new_count} новых уведомлений" if new_count > 0 else "🔔 Нет новых"
                    )
            else:
                self.all_notifications = []
                self.stats_label.setText("Нет данных")
            
            self.display_notifications()
            
        except Exception as e:
            print(f"[NOTIFICATIONS] Ошибка загрузки: {e}")
            self.all_notifications = []
            self.display_notifications()
    
    def display_notifications(self):
        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        filtered = self.get_filtered_notifications()
        
        if not filtered:
            if self.all_notifications and self._computer_filter:
                msg = f"Ничего не найдено по фильтру \"{self.filter_input.text()}\""
            elif self.all_notifications:
                msg = "Нет уведомлений по выбранному фильтру"
            else:
                msg = "Нет уведомлений"
            
            empty_label = QLabel(msg)
            empty_label.setStyleSheet("color: #95a5a6; font-size: 12px; padding: 20px; border: none;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(empty_label)
        else:
            for notif in filtered[:20]:
                item = NotificationItem(notif)
                self.content_layout.addWidget(item)
        
        self.content_layout.addStretch()


NotificationsDialog = NotificationsPopover