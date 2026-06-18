import socket
import sys
import threading
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from qtpy.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTabWidget,
                             QSystemTrayIcon, QMenu, QStatusBar, QMessageBox, QApplication)
from qtpy.QtCore import Qt, QTimer, QSettings, QThread, Signal, QPoint
from qtpy.QtGui import QIcon, QAction, QPixmap, QColor, QMouseEvent

from core.api_client import APIClient as DatabaseManager
from utils.platform_utils import get_config_dir
from ..styles import get_main_window_stylesheet
from .tabs.computers_tab import ComputersTab
from .tabs.users_tab import UsersTab
from .tabs.reports_tab import ReportsTab
from .tabs.groups_tab import GroupsTab
from ..notifications_dialog import NotificationsPopover, NotificationBadge


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения"""
    icon_path = Path(__file__).parent.parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    icon_path = Path(__file__).parent.parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(52, 152, 219))
    return QIcon(pixmap)


class AdminPanelWindow(QMainWindow):
    """Окно панели администратора с фоновым агентом"""
    
    def __init__(self, computer_data, relay_server: str = None, parent=None, background_agent=None):
        super().__init__(parent)
        self.computer_data = computer_data
        self.background_agent = background_agent
        self.tray_icon = None
        
        settings = QSettings("RemoteAccess", "Agent")
        self.relay_server = relay_server or settings.value("server", "ws://localhost:9001")
        self.quality = int(settings.value("quality", 60))
        self.fps = float(settings.value("fps", 30))
        
        self.init_ui()
        self.setup_tray()
        
        # Таймер для обновления данных (каждые 30 секунд)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_all_data)
        self.refresh_timer.start(30000)
        
        # Таймер для обновления статуса агента в нижней панели (раз в 5 секунд)
        self.agent_status_timer = QTimer()
        self.agent_status_timer.timeout.connect(self.update_agent_status_in_panel)
        self.agent_status_timer.start(5000)
        
        # Таймер для активности сессии
        self.activity_timer = QTimer()
        self.activity_timer.timeout.connect(self.update_session_activity)
        self.activity_timer.start(5 * 60 * 1000)
        
        self.update_session_activity()
        self.update_agent_status_in_panel()
    
    def update_agent_status_in_panel(self):
        """Обновляет статус агента в нижней панели (без счетчика клиентов)"""
        if self.background_agent and hasattr(self.background_agent, 'agent_instance'):
            agent = self.background_agent.agent_instance
            if agent and agent.is_connected:
                self.agent_status_label.setText("🤖 Агент активен")
                self.agent_status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
            elif agent and not agent.is_connected:
                self.agent_status_label.setText("🤖 Агент отключен")
                self.agent_status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            else:
                self.agent_status_label.setText("🤖 Агент запускается...")
                self.agent_status_label.setStyleSheet("color: #f39c12; font-size: 12px;")
        else:
            self.agent_status_label.setText("🤖 Агент не запущен")
            self.agent_status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
    
    def update_session_activity(self):
        session_id = self.computer_data.get('session_id')
        if session_id:
            try:
                DatabaseManager.update_session_activity(session_id)
                self.session_status_label.setText("● Сессия активна")
                self.session_status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
            except Exception as e:
                print(f"[ADMIN] Ошибка обновления активности: {e}")
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle("Remote Access Agent | Панель администратора")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(get_main_window_stylesheet())
        self.showMaximized()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # ========== ЗАГОЛОВОК ==========
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff8c42, stop:1 #e67e22);
                border-radius: 12px;
                padding: 10px 15px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # Строка заголовка: надпись по центру, колокольчик справа — на одной линии
        header_top_row = QHBoxLayout()
        header_top_row.setSpacing(10)
        header_top_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        title_label = QLabel("⚡ REMOTE ACCESS AGENT • ПАНЕЛЬ АДМИНИСТРАТОРА")
        title_label.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_top_row.addWidget(title_label, 1)
        
        # Колокольчик уведомлений — справа от надписи, на одной линии
        self.notifications_btn = QPushButton("🔔")
        self.notifications_btn.setObjectName("notificationsBellButton")
        self.notifications_btn.setFixedSize(36, 36)
        self.notifications_btn.setToolTip("Уведомления о событиях и аномалиях")
        BELL_STYLE = """
            QPushButton#notificationsBellButton {
                background-color: rgba(255,255,255,0.2);
                color: white;
                font-size: 18px;
                border-radius: 18px;
                padding: 0px;
                margin: 0px;
                font-weight: normal;
                border: none;
            }
            QPushButton#notificationsBellButton:hover { 
                background-color: rgba(255,255,255,0.3); 
            }
            QPushButton#notificationsBellButton:pressed { 
                background-color: rgba(255,255,255,0.4); 
            }
        """
        BELL_STYLE_CRITICAL = """
            QPushButton#notificationsBellButton {
                background-color: rgba(231,76,60,0.5);
                color: white;
                font-size: 18px;
                border-radius: 18px;
                padding: 0px;
                margin: 0px;
                font-weight: normal;
                border: none;
            }
            QPushButton#notificationsBellButton:hover { 
                background-color: rgba(231,76,60,0.7); 
            }
        """
        self.BELL_STYLE = BELL_STYLE
        self.BELL_STYLE_CRITICAL = BELL_STYLE_CRITICAL
        self.notifications_btn.setStyleSheet(BELL_STYLE)
        self.notifications_btn.clicked.connect(self.toggle_notifications)
        
        # Контейнер для колокольчика с бейджем
        bell_container = QFrame()
        bell_container.setFixedSize(50, 50)
        bell_container.setStyleSheet("background: transparent; border: none;")
        bell_container_layout = QHBoxLayout(bell_container)
        bell_container_layout.setContentsMargins(0, 0, 0, 0)
        bell_container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bell_container_layout.addWidget(self.notifications_btn)
        
        # Значок с количеством — справа сверху колокольчика
        self.notif_badge = NotificationBadge(bell_container)
        self.notif_badge.move(28, -4)
        
        header_top_row.addWidget(bell_container)
        
        header_layout.addLayout(header_top_row)
        
        main_layout.addWidget(header_frame)
        
        # ========== ВКЛАДКИ ==========
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                border-radius: 10px;
                background: white;
            }
            QTabBar::tab {
                background: #f8f9fa;
                padding: 12px 24px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
                font-size: 14px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: white;
                color: #e67e22;
                border-bottom: 2px solid #e67e22;
            }
            QTabBar::tab:hover {
                background: #e9ecef;
            }
        """)
        
        self.computers_tab = ComputersTab(self)
        self.users_tab = UsersTab(self)
        self.groups_tab = GroupsTab(self)
        self.reports_tab = ReportsTab(self)
        
        self.tab_widget.addTab(self.computers_tab, "Компьютеры")
        self.tab_widget.addTab(self.users_tab, "Пользователи")
        self.tab_widget.addTab(self.groups_tab, "Группы")
        self.tab_widget.addTab(self.reports_tab, "Отчеты")
        
        main_layout.addWidget(self.tab_widget)
        
        # ========== НИЖНЯЯ ПАНЕЛЬ ==========
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
                padding: 8px 15px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(10, 5, 10, 5)
        
        # Левая часть - статус сессии и статус агента
        left_layout = QHBoxLayout()
        
        self.session_status_label = QLabel("● Сессия активна")
        self.session_status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
        left_layout.addWidget(self.session_status_label)
        
        separator = QLabel("|")
        separator.setStyleSheet("color: #bdc3c7; font-size: 12px;")
        left_layout.addWidget(separator)
        
        # Статус агента (вместо admin)
        self.agent_status_label = QLabel("🤖 Агент активен")
        self.agent_status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
        left_layout.addWidget(self.agent_status_label)
        
        bottom_layout.addLayout(left_layout)
        bottom_layout.addStretch()
        
        # Правая часть - кнопки
        right_layout = QHBoxLayout()
        right_layout.setSpacing(10)
        
        settings_btn = QPushButton("Настройки")
        settings_btn.setMinimumHeight(32)
        settings_btn.setMinimumWidth(100)
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        settings_btn.clicked.connect(self.open_settings)
        right_layout.addWidget(settings_btn)
        
        logout_btn = QPushButton("Выйти")
        logout_btn.setMinimumHeight(32)
        logout_btn.setMinimumWidth(100)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        logout_btn.clicked.connect(self.logout)
        right_layout.addWidget(logout_btn)
        
        bottom_layout.addLayout(right_layout)
        main_layout.addWidget(bottom_frame)
        
        # Таймер для проверки уведомлений (каждые 30 секунд)
        self.notification_timer = QTimer()
        self.notification_timer.timeout.connect(self.check_notifications)
        self.notification_timer.start(30000)
        
        # Создаем экземпляр popover'а (но не показываем)
        self.notifications_popover = NotificationsPopover(self)
        
        self.refresh_all_data()
        # Первая проверка уведомлений через 2 секунды
        QTimer.singleShot(2000, self.check_notifications)
    
    def open_settings(self):
        try:
            from agent.settings_dialog import SettingsDialog
            dialog = SettingsDialog(self)
            if dialog.exec():
                dialog.save_settings()
                settings = QSettings("RemoteAccess", "Agent")
                self.relay_server = settings.value("server", "ws://localhost:9001")
                self.quality = int(settings.value("quality", 60))
                self.fps = float(settings.value("fps", 30))
                # применить настройки к агенту
                if self.background_agent and hasattr(self.background_agent, 'agent_instance'):
                    agent = self.background_agent.agent_instance
                    if agent:
                        interval = 1.0 / self.fps if self.fps > 0 else 0.05
                        agent.update_settings(interval, self.quality)
                QMessageBox.information(self, "Настройки", "Настройки сохранены и применены к агенту")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть настройки: {e}")
    
    def refresh_all_data(self):
        try:
            self.computers_tab.refresh_data()
            self.users_tab.refresh_data()
            self.groups_tab.refresh_data()
        except Exception as e:
            print(f"Ошибка обновления данных: {e}")
    
    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("PC-RMDS | Администратор | Агент активен")
        
        tray_menu = QMenu()
        show_action = QAction("Показать панель", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        agent_status_action = QAction("Статус агента", self)
        agent_status_action.triggered.connect(self.show_agent_status)
        tray_menu.addAction(agent_status_action)
        tray_menu.addSeparator()
        quit_action = QAction("Выйти", self)
        quit_action.triggered.connect(self.logout)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
    
    def show_agent_status(self):
        if self.background_agent and hasattr(self.background_agent, 'agent_instance'):
            agent = self.background_agent.agent_instance
            if agent:
                status_text = (
                    f"🤖 СТАТУС ФОНОВОГО АГЕНТА\n\n"
                    f"Состояние: {'✅ Активен' if agent.is_running else '❌ Остановлен'}\n"
                    f"Подключен к серверу: {'✅ Да' if agent.is_connected else '❌ Нет'}\n"
                    f"Клиентов: {agent.connected_clients}\n"
                    f"Трансляция: {'🟢 Активна' if agent.sending_screenshots else '⚫ Не активна'}\n"
                    f"Качество: {agent.adaptive_quality}%\n"
                    f"Сбор метрик: {'✅' if agent.is_running else '❌'}\n"
                    f"Сбор событий: {'✅' if agent.is_running else '❌'}\n"
                    f"Облачная синхронизация: {'✅' if agent.is_running else '❌'}"
                )
            else:
                status_text = "🤖 Агент запускается..."
        else:
            status_text = "🤖 Агент не запущен"
        QMessageBox.information(self, "Статус агента", status_text)
    
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
    
    def close_session(self):
        session_id = self.computer_data.get('session_id')
        if session_id:
            try:
                DatabaseManager.close_session_by_id(session_id)
            except Exception as e:
                print(f"[ADMIN] Ошибка закрытия сессии: {e}")
    
    def stop_agent(self):
        if self.background_agent:
            self.background_agent.stop()
    
    def logout(self):
        reply = QMessageBox.question(
            self, 
            "Подтверждение", 
            "Вы уверены, что хотите выйти?\n\nАгент будет остановлен.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.refresh_timer.stop()
            self.agent_status_timer.stop()
            self.activity_timer.stop()
            self.close_session()
            self.stop_agent()
            settings = QSettings("RemoteAccess", "Agent")
            settings.setValue("auto_auth", False)
            settings.sync()
            self.close()
            if self.tray_icon:
                self.tray_icon.hide()
            QApplication.quit()
    
    def closeEvent(self, event):
        self.refresh_timer.stop()
        self.agent_status_timer.stop()
        self.activity_timer.stop()
        self.notification_timer.stop()
        event.ignore()
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "PC-RMDS", 
                "Панель администратора свернута в трей\nАгент продолжает работать в фоне",
                QSystemTrayIcon.MessageIcon.Information, 
                3000
            )
    
    def toggle_notifications(self):
        """Показывает/скрывает всплывающую шторку уведомлений"""
        if self.notifications_popover and self.notifications_popover.isVisible():
            self.notifications_popover.hide_popover()
        else:
            if self.notifications_popover:
                # Перезагружаем данные
                self.notifications_popover.load_notifications()
                # Показываем под кнопкой через её глобальную позицию
                btn_global = self.notifications_btn.mapToGlobal(
                    QPoint(0, self.notifications_btn.height())
                )
                self.notifications_popover.show_popover_global(btn_global)
    
    def _on_notification_item_clicked(self, computer_id, hostname):
        """Обработчик клика по уведомлению из popover"""
        self.notifications_popover.hide_popover()
        self._open_computer_details(computer_id, hostname)
    
    def _open_computer_details(self, computer_id, hostname):
        """Открывает детали компьютера"""
        try:
            from admin.computer_details import ComputerDetailsWindow
            
            computer_data = DatabaseManager.get_computer(computer_id)
            if not computer_data:
                computer_data = {'hostname': hostname, 'computer_id': computer_id}
            
            details_window = ComputerDetailsWindow(
                hostname, computer_data,
                parent_window=self
            )
            self.hide()
            details_window.show()
        except Exception as e:
            print(f"[NOTIFICATIONS] Ошибка открытия деталей: {e}")
    
    def _count_new_notifications(self, notifications, read_until_time):
        """Считает количество уведомлений новее read_until_time"""
        if not read_until_time:
            return len(notifications)
        count = 0
        for n in notifications:
            ts = n.get('timestamp', '')
            if ts and ts > read_until_time:
                count += 1
        return count
    
    def _notification_has_critical(self, notifications, read_until_time):
        """Проверяет, есть ли критические среди новых уведомлений"""
        for n in notifications:
            ts = n.get('timestamp', '')
            if (not read_until_time or ts > read_until_time) and n.get('severity') == 'critical':
                return True
        return False
    
    def check_notifications(self):
        """Проверяет наличие новых уведомлений и обновляет бейдж"""
        try:
            data = DatabaseManager.get_recent_notifications(
                hours=24,
                cpu_threshold=85.0,
                ram_threshold=85.0,
                limit=100
            )
            
            if data:
                notifications = data.get('notifications', [])
                settings = QSettings("PC-RMDS", "Notifications")
                read_until_time = settings.value("read_until_time", "")
                
                new_count = self._count_new_notifications(notifications, read_until_time)
                has_critical = self._notification_has_critical(notifications, read_until_time)
                
                self.notif_badge.update_count(new_count)
                
                if new_count > 0:
                    self.notifications_btn.setToolTip(
                        f"🔔 {new_count} новых уведомлений"
                    )
                    if has_critical:
                        self.notifications_btn.setStyleSheet(self.BELL_STYLE_CRITICAL)
                    else:
                        self.notifications_btn.setStyleSheet(self.BELL_STYLE)
                else:
                    self.notif_badge.hide()
                    self.notifications_btn.setToolTip("🔔 Нет новых уведомлений")
                    self.notifications_btn.setStyleSheet(self.BELL_STYLE)
            else:
                self.notif_badge.hide()
                self.notifications_btn.setToolTip("🔔 Нет новых уведомлений")
                self.notifications_btn.setStyleSheet(self.BELL_STYLE)
                
        except Exception as e:
            print(f"[NOTIFICATIONS] Ошибка проверки уведомлений: {e}")
            self.notif_badge.hide()