"""Основное окно детальной информации о компьютере"""

import sys
import asyncio
import json
import base64
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from PIL import Image

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QFrame, QTabWidget, QMessageBox, 
                            QDialog, QSplitter, QApplication)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QImage

import websockets

from core.api_client import APIClient
from utils.constants import RELAY_WS_URL
from .widgets import DateRangeWidget, get_app_icon
from .overview_tab import OverviewTab
from .metrics_tab import MetricsTab
from .events_tab import EventsTab
from .sessions_tab import SessionsTab
from .anomalies_tab import AnomaliesTab
from .reports_tab import ReportsTab
from .dialogs import EditComputerDialog
from ..styles import get_main_window_stylesheet


class RemoteClientThread(QThread):
    """Поток для WebSocket соединения с relay-сервером"""
    status_updated = pyqtSignal(str, str)
    image_received = pyqtSignal(object)
    system_info_received = pyqtSignal(dict)
    connection_lost = pyqtSignal()
    
    def __init__(self, relay_server, computer_id, client_id, update_interval=0.033):
        super().__init__()
        self.relay_server = relay_server
        self.computer_id = computer_id
        self.client_id = client_id
        self.update_interval = update_interval
        self.ws = None
        self.is_running = True
        self.is_connected = False
        self.command_queue = asyncio.Queue()
        self.host_screen_width = None
        self.host_screen_height = None
        self.frame_count = 0
        self.send_task = None
        self.loop = None
    
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.client_loop())
        finally:
            self.loop.close()
    
    async def client_loop(self):
        reconnect_delay = 2
        while self.is_running:
            try:
                async with websockets.connect(self.relay_server) as websocket:
                    self.ws = websocket
                    
                    register_msg = {
                        "type": "register_client",
                        "data": {
                            "client_id": self.client_id, 
                            "computer_id": self.computer_id
                        },
                        "computer_id": self.computer_id,
                        "client_id": self.client_id
                    }
                    await self.ws.send(json.dumps(register_msg))
                    
                    self.is_connected = True
                    self.status_updated.emit("Подключен к серверу", "success")
                    
                    await self.send_command({"type": "request_system_info", "data": {}})
                    
                    self.send_task = asyncio.create_task(self.process_command_queue())
                    
                    async for msg in self.ws:
                        try:
                            data = json.loads(msg)
                            msg_type = data.get("type")
                            
                            if msg_type == "screenshot":
                                img_data = base64.b64decode(data["data"])
                                img = Image.open(BytesIO(img_data))
                                
                                self.host_screen_width = data.get("screen_width", img.size[0])
                                self.host_screen_height = data.get("screen_height", img.size[1])
                                self.image_received.emit(img)
                                self.frame_count += 1
                            
                            elif msg_type == "system_info":
                                system_data = data.get("data", {})
                                self.system_info_received.emit(system_data)
                            
                        except Exception as e:
                            pass
                    
            except Exception as e:
                self.status_updated.emit(f"Ошибка: {str(e)}", "error")
            
            self.is_connected = False
            if self.send_task:
                self.send_task.cancel()
                try:
                    await self.send_task
                except:
                    pass
            self.connection_lost.emit()
            
            if self.is_running:
                await asyncio.sleep(reconnect_delay)
    
    async def process_command_queue(self):
        while self.is_connected and self.is_running:
            try:
                try:
                    command = await asyncio.wait_for(self.command_queue.get(), timeout=0.1)
                    await self.send_command(command)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except:
                await asyncio.sleep(0.1)
    
    async def send_command(self, command):
        if self.ws and self.is_connected:
            try:
                message = {
                    "type": command.get("type", "command"),
                    "data": command.get("data", {}),
                    "computer_id": self.computer_id,
                    "client_id": self.client_id
                }
                await self.ws.send(json.dumps(message))
                return True
            except Exception as e:
                return False
        return False
    
    def queue_command(self, command):
        if self.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(
                self._queue_command_async(command), 
                self.loop
            )
    
    async def _queue_command_async(self, command):
        await self.command_queue.put(command)
    
    def request_system_info(self):
        if self.is_connected:
            self.queue_command({"type": "request_system_info", "data": {}})
    
    def start_stream(self):
        if self.is_connected:
            self.queue_command({"type": "start_stream", "data": {}})
    
    def stop_stream(self):
        if self.is_connected:
            self.queue_command({"type": "stop_stream", "data": {}})
    
    def stop(self):
        self.is_running = False
        self.is_connected = False
        if self.send_task:
            asyncio.run_coroutine_threadsafe(self._cancel_task(), self.loop)
    
    async def _cancel_task(self):
        if self.send_task:
            self.send_task.cancel()
            try:
                await self.send_task
            except:
                pass


class RemoteScreenWidget(QLabel):
    """Виджет для отображения удаленного экрана с обработкой ввода"""
    mouse_moved = pyqtSignal(int, int, int, int)
    mouse_clicked = pyqtSignal(str, int, int)
    mouse_wheeled = pyqtSignal(int)
    key_pressed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.host_screen_width = None
        self.host_screen_height = None
        self.display_image_width = 0
        self.display_image_height = 0
        self.image_offset_x = 0
        self.image_offset_y = 0
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
    
    def set_display_info(self, host_width, host_height, display_width, display_height):
        self.host_screen_width = host_width
        self.host_screen_height = host_height
        self.display_image_width = display_width
        self.display_image_height = display_height
        
        if host_width and host_height and display_width and display_height:
            self.scale_x = host_width / display_width
            self.scale_y = host_height / display_height
        else:
            self.scale_x = 1.0
            self.scale_y = 1.0
    
    def update_image_position(self):
        pixmap = self.pixmap()
        if pixmap:
            self.image_offset_x = (self.width() - pixmap.width()) // 2
            self.image_offset_y = (self.height() - pixmap.height()) // 2
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_position()
    
    def client_to_host_coords(self, client_x, client_y):
        if not (self.host_screen_width and self.host_screen_height):
            return client_x, client_y
        
        pixmap = self.pixmap()
        if not pixmap or pixmap.width() == 0 or pixmap.height() == 0:
            return client_x, client_y
        
        pixmap_width = pixmap.width()
        pixmap_height = pixmap.height()
        
        scale_x = self.host_screen_width / pixmap_width
        scale_y = self.host_screen_height / pixmap_height
        
        host_x = int(client_x * scale_x)
        host_y = int(client_y * scale_y)
        
        host_x = max(0, min(host_x, self.host_screen_width - 1))
        host_y = max(0, min(host_y, self.host_screen_height - 1))
        
        return host_x, host_y
    
    def get_image_coords(self, widget_x, widget_y):
        pixmap = self.pixmap()
        if pixmap:
            img_left = self.image_offset_x
            img_right = img_left + pixmap.width()
            img_top = self.image_offset_y
            img_bottom = img_top + pixmap.height()
            
            if (img_left <= widget_x <= img_right and 
                img_top <= widget_y <= img_bottom):
                
                img_x = widget_x - img_left
                img_y = widget_y - img_top
                
                return img_x, img_y
        
        return None, None
    
    def mouseMoveEvent(self, event):
        if self.host_screen_width and self.host_screen_height:
            img_x, img_y = self.get_image_coords(
                int(event.position().x()), 
                int(event.position().y())
            )
            
            if img_x is not None and img_y is not None:
                host_x, host_y = self.client_to_host_coords(img_x, img_y)
                self.mouse_moved.emit(img_x, img_y, host_x, host_y)
    
    def mousePressEvent(self, event):
        if self.host_screen_width and self.host_screen_height:
            img_x, img_y = self.get_image_coords(
                int(event.position().x()), 
                int(event.position().y())
            )
            
            if img_x is not None and img_y is not None:
                host_x, host_y = self.client_to_host_coords(img_x, img_y)
                
                if event.button() == Qt.MouseButton.LeftButton:
                    button = "left"
                elif event.button() == Qt.MouseButton.RightButton:
                    button = "right"
                else:
                    button = "middle"
                
                self.mouse_clicked.emit(button, host_x, host_y)
    
    def wheelEvent(self, event):
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.mouse_wheeled.emit(delta)
    
    def keyPressEvent(self, event):
        text = event.text()
        
        if text:
            self.key_pressed.emit(text)
        else:
            key = event.key()
            if key == Qt.Key.Key_Backspace:
                self.key_pressed.emit('\b')
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self.key_pressed.emit('\r')
            elif key == Qt.Key.Key_Tab:
                self.key_pressed.emit('\t')
            elif key == Qt.Key.Key_Escape:
                self.key_pressed.emit('\x1b')
            elif key == Qt.Key.Key_Delete:
                self.key_pressed.emit('\x7f')
            elif key == Qt.Key.Key_Left:
                self.key_pressed.emit('\x1b[D')
            elif key == Qt.Key.Key_Right:
                self.key_pressed.emit('\x1b[C')
            elif key == Qt.Key.Key_Up:
                self.key_pressed.emit('\x1b[A')
            elif key == Qt.Key.Key_Down:
                self.key_pressed.emit('\x1b[B')
            elif key == Qt.Key.Key_Home:
                self.key_pressed.emit('\x1b[H')
            elif key == Qt.Key.Key_End:
                self.key_pressed.emit('\x1b[F')
            elif key == Qt.Key.Key_PageUp:
                self.key_pressed.emit('\x1b[5~')
            elif key == Qt.Key.Key_PageDown:
                self.key_pressed.emit('\x1b[6~')
        
        super().keyPressEvent(event)
    
    def set_screen_size(self, width, height):
        self.host_screen_width = width
        self.host_screen_height = height
    
    def clear_screen(self):
        self.clear()
        self.setText("Соединение потеряно")
        self.setStyleSheet("background-color: black; color: red; font-size: 16px;")


class RemoteScreenWindow(QMainWindow):
    """Окно для отображения удаленного экрана"""
    key_pressed = pyqtSignal(str)
    closed = pyqtSignal()
    
    def __init__(self, client_thread, computer_name=""):
        super().__init__()
        self.client_thread = client_thread
        self.frame_count = 0
        self.original_width = 0
        self.original_height = 0
        self.display_width = 0
        self.display_height = 0
        self.computer_name = computer_name
        self.init_ui()
        
        self.screen_widget.mouse_moved.connect(self.on_mouse_move)
        self.screen_widget.mouse_clicked.connect(self.on_mouse_click)
        self.screen_widget.mouse_wheeled.connect(self.on_mouse_wheel)
        self.screen_widget.key_pressed.connect(self.on_key_press)
    
    def init_ui(self):
        self.setWindowTitle(f"Удаленный экран - {self.computer_name}")
        self.setGeometry(200, 200, 1280, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Верхняя панель
        status_bar = QFrame()
        status_bar.setStyleSheet("background-color: #2c3e50;")
        status_bar.setFixedHeight(35)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 0, 10, 0)
        
        self.status_label = QLabel(f"Подключение к {self.computer_name}...")
        self.status_label.setStyleSheet("color: white; font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("color: #3498db; font-size: 11px; font-weight: bold;")
        status_layout.addWidget(self.fps_label)
        
        self.resolution_label = QLabel("")
        self.resolution_label.setStyleSheet("color: white; font-size: 11px;")
        status_layout.addWidget(self.resolution_label)
        
        # Кнопка закрытия
        close_btn = QPushButton("✕ Закрыть")
        close_btn.setFixedSize(80, 25)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        close_btn.clicked.connect(self.close)
        status_layout.addWidget(close_btn)
        
        layout.addWidget(status_bar)
        
        # Виджет экрана
        self.screen_widget = RemoteScreenWidget()
        self.screen_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.screen_widget, 1)
        
        QTimer.singleShot(100, self.set_focus)
    
    def set_focus(self):
        self.screen_widget.setFocus()
        self.activateWindow()
        self.raise_()
    
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.set_focus)
    
    def update_image(self, img):
        widget_size = self.screen_widget.size()
        if widget_size.width() <= 1 or widget_size.height() <= 1:
            return
        
        host_width = self.client_thread.host_screen_width or img.width
        host_height = self.client_thread.host_screen_height or img.height
        
        self.original_width = img.width
        self.original_height = img.height
        
        img_ratio = img.width / img.height
        widget_ratio = widget_size.width() / widget_size.height()
        
        if img_ratio > widget_ratio:
            new_width = widget_size.width()
            new_height = int(widget_size.width() / img_ratio)
        else:
            new_height = widget_size.height()
            new_width = int(widget_size.height() * img_ratio)
        
        if new_width > 0 and new_height > 0:
            self.display_width = new_width
            self.display_height = new_height
            
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            img_byte_array = BytesIO()
            img_resized.save(img_byte_array, format='PNG')
            qimage = QImage.fromData(img_byte_array.getvalue())
            pixmap = QPixmap.fromImage(qimage)
            
            self.screen_widget.setPixmap(pixmap)
            
            actual_pixmap_width = pixmap.width()
            actual_pixmap_height = pixmap.height()
            self.screen_widget.set_display_info(
                host_width, host_height,
                actual_pixmap_width, actual_pixmap_height
            )
            
            self.screen_widget.set_screen_size(host_width, host_height)
            self.screen_widget.update_image_position()
            self.frame_count += 1
            
            scale_percent = int((new_width / img.width) * 100)
            self.resolution_label.setText(
                f"Сервер: {host_width}x{host_height} | "
                f"Экран: {new_width}x{new_height} | "
                f"Масштаб: {scale_percent}%"
            )
            self.status_label.setText(f"Подключен к {self.computer_name}")
            self.status_label.setStyleSheet("color: #2ecc71; font-size: 12px;")
    
    def update_fps(self, fps):
        self.fps_label.setText(f"FPS: {fps}")
    
    def clear_screen(self):
        self.screen_widget.clear_screen()
        self.status_label.setText("Соединение потеряно")
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
    
    def on_mouse_move(self, client_x, client_y, host_x, host_y):
        self.client_thread.queue_command({
            "type": "mouse_move",
            "data": {"x": host_x, "y": host_y}
        })
    
    def on_mouse_click(self, button, host_x, host_y):
        self.client_thread.queue_command({
            "type": "mouse_click",
            "data": {"button": button, "x": host_x, "y": host_y}
        })
    
    def on_mouse_wheel(self, delta):
        self.client_thread.queue_command({
            "type": "mouse_wheel",
            "data": {"delta": delta}
        })
    
    def on_key_press(self, text):
        self.key_pressed.emit(text)
    
    def closeEvent(self, event):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.stop_stream()
        self.closed.emit()
        event.accept()


class ComputerDetailsWindow(QMainWindow):
    """Окно с детальной информацией по компьютеру"""
    
    def __init__(self, hostname, computer_data, user_login=None, parent_window=None):
        super().__init__()
        self.hostname = hostname
        self.computer_data = computer_data
        self.user_login = user_login or computer_data.get('login', 'Admin')
        self.parent_window = parent_window
        self.current_data = None
        self.computer_id = None
        self.current_disk_info = {'used_gb': None, 'total_gb': None}
        
        # Переменные для удаленного доступа
        self.remote_client_thread = None
        self.remote_window = None
        self.frame_count = 0
        self.fps_timer = None
        
        self.init_ui()
        self.connect_signals()
        self.load_computer_info()
        
        QTimer.singleShot(500, self.refresh_all_data)
    
    def init_ui(self):
        self.setWindowTitle(f"PC-RMDS | {self.computer_data.get('hostname', 'Unknown')}")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(get_main_window_stylesheet())
        self.setWindowIcon(get_app_icon())
        self.showMaximized()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff8c42, stop:1 #e67e22);
                border-radius: 12px;
                padding: 0px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        
        self.title_label = QLabel(self.computer_data.get('hostname', 'Unknown'))
        self.title_label.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label)
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.status_label)
        
        # Кнопки в заголовке
        header_buttons_layout = QHBoxLayout()
        header_buttons_layout.addStretch()
        
        self.remote_btn = QPushButton("🖥 Удаленный экран")
        self.remote_btn.setFixedWidth(150)
        self.remote_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.3);
            }
            QPushButton:disabled {
                background-color: rgba(255,255,255,0.1);
            }
        """)
        self.remote_btn.clicked.connect(self.open_remote_screen)
        header_buttons_layout.addWidget(self.remote_btn)
        
        edit_btn = QPushButton("✎ Редактировать")
        edit_btn.setFixedWidth(120)
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.3);
            }
        """)
        edit_btn.clicked.connect(self.edit_computer_info)
        header_buttons_layout.addWidget(edit_btn)
        
        header_layout.addLayout(header_buttons_layout)
        
        main_layout.addWidget(header_frame)
        
        # Выбор периода
        self.date_range = DateRangeWidget()
        main_layout.addWidget(self.date_range)
        
        # Табы
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #ff8c42;
                color: white;
            }
        """)
        
        self.overview_tab = OverviewTab(self)
        self.tabs.addTab(self.overview_tab, "Общая информация")
        
        self.metrics_tab = MetricsTab(self)
        self.tabs.addTab(self.metrics_tab, "Метрики")
        
        self.events_tab = EventsTab(self)
        self.tabs.addTab(self.events_tab, "События")
        
        self.sessions_tab = SessionsTab(self)
        self.tabs.addTab(self.sessions_tab, "Сессии")
        
        self.anomalies_tab = AnomaliesTab(self)
        self.tabs.addTab(self.anomalies_tab, "Аномалии")
        
        self.reports_tab = ReportsTab(self)
        self.tabs.addTab(self.reports_tab, "Отчеты")
        
        main_layout.addWidget(self.tabs)
        
        # Нижняя панель с кнопками
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        back_btn = QPushButton("Назад")
        back_btn.clicked.connect(self.go_back)
        back_btn.setMinimumWidth(120)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        btn_layout.addWidget(back_btn)
        
        main_layout.addLayout(btn_layout)
    
    def connect_signals(self):
        self.date_range.periodChanged.connect(self.refresh_all_data)
    
    def edit_computer_info(self):
        if not self.computer_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера не определен")
            return
        
        dialog = EditComputerDialog(self.current_data, self.computer_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            update_data = dialog.get_update_data()
            if update_data:
                self.save_computer_info(update_data)
    
    def save_computer_info(self, update_data):
        try:
            result = APIClient.put(f'/api/computers/{self.computer_id}', json=update_data)
            if result and result.get('success'):
                QMessageBox.information(self, "Успех", "Информация о компьютере обновлена")
                self.load_computer_info()
                self.refresh_all_data()
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось обновить информацию")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка при обновлении: {e}")
    
    def load_computer_info(self):
        try:
            result = APIClient.get('/computers', params={'search': self.hostname})
            if result and result.get('success'):
                computers_data = result.get('data', {})
                computers = computers_data.get('computers', [])
                for comp in computers:
                    if comp.get('hostname') == self.hostname:
                        self.computer_id = comp.get('computer_id')
                        break
            
            if self.computer_id:
                result = APIClient.get(f'/computers/{self.computer_id}')
                if result and result.get('success'):
                    self.current_data = result.get('data', {})
                    if self.current_data.get('group_id'):
                        group_result = APIClient.get(f'/computers/groups/{self.current_data["group_id"]}')
                        if group_result and group_result.get('success'):
                            self.current_data['group_name'] = group_result['data'].get('group_name', '—')
                    else:
                        self.current_data['group_name'] = '—'
                else:
                    self.current_data = self.computer_data
                    self.current_data['group_name'] = '—'
            else:
                self.current_data = self.computer_data
                self.current_data['group_name'] = '—'
            
            is_online = self.current_data.get('is_online', False)
            self.status_label.setText("В сети" if is_online else "Не в сети")
            
            self.overview_tab.update_computer_info(self.current_data, self.current_disk_info)
            
        except Exception as e:
            print(f"Ошибка загрузки информации: {e}")
    
    def refresh_all_data(self):
        if not self.computer_id:
            self.load_computer_info()
            if not self.computer_id:
                return
        
        self.load_overview_summary()
        self.load_metrics()
        self.load_events()
        self.load_sessions()
        self.load_anomalies()
        self.load_disk_space()
    
    def load_overview_summary(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/average', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                avg_data = data.get('average', {})
                
                cpu = avg_data.get('cpu_usage')
                ram = avg_data.get('ram_usage')
                disk = avg_data.get('disk_usage')
                network_sent = avg_data.get('network_sent_mb', 0)
                network_recv = avg_data.get('network_recv_mb', 0)
                network_total = network_sent + network_recv
                
                self.overview_tab.update_summary('cpu_avg', cpu if cpu else "—")
                self.overview_tab.update_summary('ram_avg', ram if ram else "—")
                self.overview_tab.update_summary('disk_avg', disk if disk else "—")
                self.overview_tab.update_summary('network_total', network_total)
        except Exception as e:
            print(f"Ошибка загрузки средних метрик: {e}")
        
        try:
            result = APIClient.get('/metrics/events/statistics', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                total_events = data.get('total_events', 0)
                self.overview_tab.update_summary('events_total', total_events)
        except Exception as e:
            print(f"Ошибка загрузки статистики событий: {e}")
        
        try:
            result = APIClient.get('/metrics/anomalies', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to'],
                'cpu_threshold': 0,
                'ram_threshold': 0
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                anomalies_count = data.get('count', 0)
                self.overview_tab.update_summary('anomalies_total', anomalies_count)
        except Exception as e:
            print(f"Ошибка загрузки общего количества аномалий: {e}")
    
    def load_metrics(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/performance', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                metrics = data.get('performance', [])
                self.metrics_tab.update_metrics(metrics)
            else:
                self.metrics_tab.update_metrics([])
        except Exception as e:
            print(f"Ошибка загрузки метрик: {e}")
            self.metrics_tab.update_metrics([])
    
    def load_events(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/events/statistics', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                statistics = data.get('statistics', {})
                
                events_result = APIClient.get('/metrics/events', params={
                    'computer_id': self.computer_id,
                    'from': period['from'],
                    'to': period['to']
                })
                if events_result and events_result.get('success'):
                    events_data = events_result.get('data', {})
                    events = events_data.get('events', [])
                    self.events_tab.update_events(events, statistics)
            else:
                self.events_tab.update_events([], {})
        except Exception as e:
            print(f"Ошибка загрузки событий: {e}")
            self.events_tab.update_events([], {})
    
    def load_sessions(self):
        if not self.computer_id:
            return
        
        try:
            result = APIClient.get(f'/computers/{self.computer_id}/sessions')
            
            if result and result.get('success'):
                data = result.get('data', {})
                sessions = data.get('sessions', [])
                self.sessions_tab.update_sessions(sessions)
            else:
                self.sessions_tab.update_sessions([])
        except Exception as e:
            print(f"Ошибка загрузки сессий: {e}")
            self.sessions_tab.update_sessions([])
    
    def load_anomalies(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        cpu_thresh, ram_thresh = self.anomalies_tab.get_thresholds()
        
        try:
            result = APIClient.get('/metrics/anomalies', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to'],
                'cpu_threshold': cpu_thresh,
                'ram_threshold': ram_thresh
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                anomalies = data.get('anomalies', [])
                self.anomalies_tab.update_anomalies(anomalies, cpu_thresh, ram_thresh)
            else:
                self.anomalies_tab.update_anomalies([], cpu_thresh, ram_thresh)
        except Exception as e:
            print(f"Ошибка загрузки аномалий: {e}")
            self.anomalies_tab.update_anomalies([], cpu_thresh, ram_thresh)
    
    def load_disk_space(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/performance', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to'],
                'limit': 1
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                metrics = data.get('performance', [])
                if metrics:
                    last_metric = metrics[-1]
                    self.current_disk_info['used_gb'] = last_metric.get('disk_used_gb')
                    self.current_disk_info['total_gb'] = last_metric.get('disk_total_gb')
                    
                    self.overview_tab.disk_widget.update_disk_info(
                        self.current_disk_info['used_gb'],
                        self.current_disk_info['total_gb']
                    )
                    return
            
            total_gb = self.current_data.get('storage_total')
            if total_gb:
                self.current_disk_info['total_gb'] = float(total_gb)
                self.overview_tab.disk_widget.update_disk_info(
                    self.current_disk_info.get('used_gb'),
                    self.current_disk_info.get('total_gb')
                )
        except Exception as e:
            print(f"Ошибка загрузки информации о диске: {e}")
    
    # ==================== Методы удаленного доступа ====================
    
    def open_remote_screen(self):
        """Открывает окно удаленного экрана"""
        if not self.computer_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера не определен")
            return
        
        # Проверяем онлайн статус
        is_online = self.current_data.get('is_online', False) if self.current_data else False
        if not is_online:
            reply = QMessageBox.question(
                self, "Подтверждение",
                f"Компьютер {self.hostname} не в сети.\n"
                "Удаленный доступ может быть недоступен.\n"
                "Продолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Если уже есть активное подключение
        if self.remote_window and self.remote_window.isVisible():
            self.remote_window.raise_()
            self.remote_window.activateWindow()
            return
        
        # Если уже есть поток, но окно закрыто - пересоздаем
        if self.remote_client_thread and self.remote_client_thread.isRunning():
            self.disconnect_remote()
        
        # Используем адрес сервера из констант
        relay_server = RELAY_WS_URL
        
        # Создаем клиентский поток
        client_id = f"ADMIN_{self.user_login}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        self.remote_client_thread = RemoteClientThread(
            relay_server=relay_server,
            computer_id=str(self.computer_id),
            client_id=client_id,
            update_interval=0.033
        )
        
        # Подключаем сигналы
        self.remote_client_thread.status_updated.connect(self.on_remote_status_updated)
        self.remote_client_thread.image_received.connect(self.on_remote_image_received)
        self.remote_client_thread.connection_lost.connect(self.on_remote_connection_lost)
        
        # Запускаем поток
        self.remote_client_thread.start()
        
        # Создаем таймер для FPS
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_remote_fps)
        
        # Показываем индикатор загрузки
        self.remote_btn.setEnabled(False)
        self.remote_btn.setText("🖥 Подключение...")
    
    def on_remote_status_updated(self, message, msg_type):
        """Обработчик обновления статуса удаленного подключения"""
        if msg_type == "success":
            self.remote_btn.setText("🖥 Удаленный экран")
            self.remote_btn.setEnabled(True)
            
            # Запускаем стрим и создаем окно
            QTimer.singleShot(500, self._create_remote_window)
            
        elif msg_type == "error":
            self.remote_btn.setText("🖥 Удаленный экран")
            self.remote_btn.setEnabled(True)
            QMessageBox.warning(self, "Ошибка", f"Ошибка подключения: {message}")
    
    def _create_remote_window(self):
        """Создает окно удаленного экрана"""
        if not self.remote_client_thread or not self.remote_client_thread.is_connected:
            return
        
        # Запускаем стрим
        self.remote_client_thread.start_stream()
        
        # Создаем окно
        computer_name = self.hostname
        self.remote_window = RemoteScreenWindow(self.remote_client_thread, computer_name)
        self.remote_window.key_pressed.connect(self.on_remote_key_press)
        self.remote_window.closed.connect(self.on_remote_window_closed)
        self.remote_window.show()
        
        # Запускаем таймер FPS
        self.frame_count = 0
        self.fps_timer.start(1000)
    
    def on_remote_image_received(self, img):
        """Обработчик получения изображения"""
        if self.remote_window and self.remote_window.isVisible():
            self.remote_window.update_image(img)
            self.frame_count += 1
    
    def on_remote_connection_lost(self):
        """Обработчик потери соединения"""
        if self.remote_window:
            self.remote_window.clear_screen()
        
        self.remote_btn.setText("🖥 Удаленный экран")
        self.remote_btn.setEnabled(True)
        
        if self.fps_timer:
            self.fps_timer.stop()
    
    def on_remote_window_closed(self):
        """Обработчик закрытия окна удаленного экрана"""
        if self.remote_client_thread and self.remote_client_thread.is_connected:
            self.remote_client_thread.stop_stream()
        
        self.remote_window = None
        
        if self.fps_timer:
            self.fps_timer.stop()
            self.fps_timer = None
        
        self.remote_btn.setText("🖥 Удаленный экран")
        self.remote_btn.setEnabled(True)
    
    def on_remote_key_press(self, text):
        """Обработчик нажатия клавиш в окне удаленного экрана"""
        if self.remote_client_thread and self.remote_client_thread.is_connected:
            self.remote_client_thread.queue_command({
                "type": "keyboard_input",
                "data": {"text": text}
            })
    
    def update_remote_fps(self):
        """Обновляет FPS в окне удаленного экрана"""
        if self.remote_window and self.remote_window.isVisible():
            self.remote_window.update_fps(self.frame_count)
        self.frame_count = 0
    
    def disconnect_remote(self):
        """Отключает удаленное подключение"""
        if self.remote_client_thread:
            if self.remote_client_thread.is_connected:
                self.remote_client_thread.stop_stream()
            self.remote_client_thread.stop()
            self.remote_client_thread = None
        
        if self.remote_window:
            self.remote_window.close()
            self.remote_window = None
        
        if self.fps_timer:
            self.fps_timer.stop()
            self.fps_timer = None
        
        self.remote_btn.setText("🖥 Удаленный экран")
        self.remote_btn.setEnabled(True)
    
    # ==================== Конец методов удаленного доступа ====================
    
    def go_back(self):
        if self.parent_window:
            self.parent_window.show()
        self.close()
    
    def closeEvent(self, event):
        # Отключаем удаленный доступ при закрытии
        self.disconnect_remote()
        
        if self.parent_window:
            self.parent_window.show()
        event.accept()
