import socket
import sys
import threading
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from qtpy.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTabWidget,
                             QSystemTrayIcon, QMenu, QStatusBar, QMessageBox, QApplication)
from qtpy.QtCore import Qt, QTimer, QSettings, QThread, Signal
from qtpy.QtGui import QIcon, QAction, QPixmap, QColor

from core.api_client import APIClient as DatabaseManager
from utils.platform_utils import get_config_dir
from ..styles import get_main_window_stylesheet
from .tabs.computers_tab import ComputersTab
from .tabs.users_tab import UsersTab
from .tabs.reports_tab import ReportsTab


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
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # ========== ЗАГОЛОВОК ==========
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
        
        title_label = QLabel("⚡ REMOTE ACCESS AGENT • ПАНЕЛЬ АДМИНИСТРАТОРА")
        title_label.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        
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
        self.reports_tab = ReportsTab(self)
        
        self.tab_widget.addTab(self.computers_tab, "Компьютеры")
        self.tab_widget.addTab(self.users_tab, "Пользователи")
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
        
        settings_btn = QPushButton("⚙ Настройки")
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
        
        logout_btn = QPushButton("🚪 Выйти")
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
        
        self.refresh_all_data()
    
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
        except Exception as e:
            print(f"Ошибка обновления данных: {e}")
    
    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("PC-RMDS | Администратор | Агент активен")
        
        tray_menu = QMenu()
        show_action = QAction("👁 Показать панель", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        settings_action = QAction("⚙ Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        agent_status_action = QAction("🤖 Статус агента", self)
        agent_status_action.triggered.connect(self.show_agent_status)
        tray_menu.addAction(agent_status_action)
        tray_menu.addSeparator()
        quit_action = QAction("✖ Выйти", self)
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
        event.ignore()
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "PC-RMDS", 
                "Панель администратора свернута в трей\nАгент продолжает работать в фоне",
                QSystemTrayIcon.MessageIcon.Information, 
                3000
            )