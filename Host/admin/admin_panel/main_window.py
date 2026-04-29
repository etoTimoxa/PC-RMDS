import socket
from datetime import datetime, timedelta
from qtpy.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTabWidget,
                             QSystemTrayIcon, QMenu, QStatusBar, QMessageBox, QApplication)
from qtpy.QtCore import Qt, QTimer, QSettings
from qtpy.QtGui import QIcon, QAction, QPixmap, QColor

from core.api_client import APIClient as DatabaseManager
from utils.platform_utils import get_config_dir
from ..styles import get_main_window_stylesheet
from .tabs.computers_tab import ComputersTab
from .tabs.users_tab import UsersTab
from .tabs.reports_tab import ReportsTab


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения"""
    from pathlib import Path
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
    """Окно панели администратора"""
    
    def __init__(self, computer_data, parent=None):
        super().__init__(parent)
        self.computer_data = computer_data
        self.tray_icon = None
        
        self.init_ui()
        self.setup_tray()
        
        # Таймер для обновления данных (каждые 30 секунд)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_all_data)
        self.refresh_timer.start(30000)
        
        # Таймер для обновления активности сессии (каждые 5 минут)
        self.activity_timer = QTimer()
        self.activity_timer.timeout.connect(self.update_session_activity)
        self.activity_timer.start(5 * 60 * 1000)
        
        # Сразу обновляем активность при запуске
        self.update_session_activity()
    
    def update_session_activity(self):
        """Обновляет активность сессии администратора"""
        session_id = self.computer_data.get('session_id')
        if session_id:
            try:
                success = DatabaseManager.update_session_activity(session_id)
                if success:
                    print(f"[ADMIN] ✅ Активность сессии {session_id} обновлена")
                else:
                    print(f"[ADMIN] ⚠️ Не удалось обновить активность сессии {session_id}")
            except Exception as e:
                print(f"[ADMIN] ❌ Ошибка обновления активности: {e}")
    
    def init_ui(self):
        self.setWindowIcon(get_app_icon())
        self.setWindowTitle(f"Remote Access Agent | Администратор")
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
        
        # Вкладки панели
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
        
        # Создаем вкладки
        self.computers_tab = ComputersTab(self)
        self.users_tab = UsersTab(self)
        self.reports_tab = ReportsTab(self)
        
        self.tab_widget.addTab(self.computers_tab, "Компьютеры")
        self.tab_widget.addTab(self.users_tab, "Пользователи")
        self.tab_widget.addTab(self.reports_tab, "Отчеты")
        
        main_layout.addWidget(self.tab_widget)
        
        # Нижняя панель
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # Индикатор статуса сессии
        self.session_status_label = QLabel("● Сессия активна")
        self.session_status_label.setStyleSheet("color: #27ae60; font-size: 12px; padding: 5px;")
        btn_layout.addWidget(self.session_status_label)
        
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
        
        self.statusBar().showMessage(f"Администратор: {self.computer_data.get('login', 'Unknown')} | PC-RMDS | Сессия ID: {self.computer_data.get('session_id', 'N/A')}")
        
        # Загружаем данные
        self.refresh_all_data()
    
    def refresh_all_data(self):
        """Обновляет данные во всех вкладках"""
        try:
            self.computers_tab.refresh_data()
            self.users_tab.refresh_data()
        except Exception as e:
            print(f"Ошибка обновления данных: {e}")
    
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
    
    def close_session(self):
        """Закрывает сессию администратора"""
        session_id = self.computer_data.get('session_id')
        if session_id:
            print(f"[ADMIN] Закрытие сессии {session_id}...")
            try:
                DatabaseManager.close_session_by_id(session_id)
                print(f"[ADMIN] ✅ Сессия {session_id} закрыта")
            except Exception as e:
                print(f"[ADMIN] ❌ Ошибка закрытия сессии: {e}")
        else:
            print(f"[ADMIN] ⚠️ Нет активной сессии для закрытия")
    
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
            # Останавливаем таймеры
            self.refresh_timer.stop()
            self.activity_timer.stop()
            
            # Закрываем сессию перед выходом
            self.close_session()
            
            settings = QSettings("RemoteAccess", "Agent")
            settings.setValue("auto_auth", False)
            settings.sync()
            
            self.close()
            if self.tray_icon:
                self.tray_icon.hide()
            QApplication.quit()
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        # Останавливаем таймеры
        self.refresh_timer.stop()
        self.activity_timer.stop()
        
        # Закрываем сессию при закрытии окна
        self.close_session()
        
        event.ignore()
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "PC-RMDS",
                "Приложение свернуто в трей",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )