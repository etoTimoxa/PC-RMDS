import sys
import asyncio
import websockets
import json
import base64
from io import BytesIO
import time
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTabWidget, QTextEdit, QFrame, QMessageBox,
                            QGroupBox, QGridLayout, QSplitter, QTableWidget, 
                            QTableWidgetItem, QHeaderView, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage, QFont, QColor

from PIL import Image


class MetricsTableWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("МЕТРИКИ КОМПЬЮТЕРА")
        title.setStyleSheet("""
            QLabel {
                background-color: #3498db;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        self.update_time_label = QLabel("Последнее обновление: никогда")
        self.update_time_label.setStyleSheet("color: gray; padding: 2px;")
        layout.addWidget(self.update_time_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Параметр", "Значение"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #bdc3c7;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        
        self.update_table({})
        layout.addWidget(self.table)
        
        self.refresh_btn = QPushButton("ОБНОВИТЬ МЕТРИКИ")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
                margin-top: 5px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        layout.addWidget(self.refresh_btn)
        
        self.setLayout(layout)
    
    def update_table(self, metrics):
        rows = [
            ("CPU", f"{metrics.get('cpu_usage', 0)}%"),
            ("RAM", f"{metrics.get('ram_usage', 0)}% ({metrics.get('ram_used_gb', 0)} GB / {metrics.get('ram_total_gb', 0)} GB)"),
            ("Диск", f"{metrics.get('disk_usage', 0)}% ({metrics.get('disk_used_gb', 0)} GB / {metrics.get('disk_total_gb', 0)} GB)"),
        ]
        
        self.table.setRowCount(len(rows))
        for i, (param, value) in enumerate(rows):
            param_item = QTableWidgetItem(param)
            param_item.setFlags(param_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            value_item = QTableWidgetItem(value)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            if i == 0:
                cpu = metrics.get('cpu_usage', 0)
                if cpu > 90:
                    value_item.setForeground(QColor(255, 0, 0))
                elif cpu > 70:
                    value_item.setForeground(QColor(255, 165, 0))
            elif i == 1:
                ram = metrics.get('ram_usage', 0)
                if ram > 90:
                    value_item.setForeground(QColor(255, 0, 0))
                elif ram > 70:
                    value_item.setForeground(QColor(255, 165, 0))
            
            self.table.setItem(i, 0, param_item)
            self.table.setItem(i, 1, value_item)
        
        events = metrics.get('events', [])
        if events:
            current_row = self.table.rowCount()
            self.table.setRowCount(current_row + len(events))
            for i, event in enumerate(events):
                warning_item = QTableWidgetItem(f"! {event.get('event_source', 'Warning')}")
                warning_item.setForeground(QColor(255, 0, 0))
                warning_item.setFlags(warning_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                desc_item = QTableWidgetItem(event.get('description', ''))
                desc_item.setForeground(QColor(255, 0, 0))
                desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                self.table.setItem(current_row + i, 0, warning_item)
                self.table.setItem(current_row + i, 1, desc_item)


class SystemInfoDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        top_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("ОБНОВИТЬ ИНФОРМАЦИЮ")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        top_layout.addWidget(self.refresh_btn)
        
        self.update_time_label = QLabel("Последнее обновление: никогда")
        self.update_time_label.setStyleSheet("color: gray;")
        top_layout.addWidget(self.update_time_label)
        layout.addLayout(top_layout)
        
        basic_group = QGroupBox("Основная информация")
        font = QFont("Arial", 10, QFont.Weight.Bold)
        basic_group.setFont(font)
        basic_layout = QVBoxLayout()
        self.basic_info = QTextEdit()
        self.basic_info.setFont(QFont("Consolas", 9))
        self.basic_info.setMaximumHeight(100)
        self.basic_info.setReadOnly(True)
        basic_layout.addWidget(self.basic_info)
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        hw_group = QGroupBox("Конфигурация оборудования")
        hw_group.setFont(font)
        hw_layout = QVBoxLayout()
        self.hw_info = QTextEdit()
        self.hw_info.setFont(QFont("Consolas", 9))
        self.hw_info.setMaximumHeight(120)
        self.hw_info.setReadOnly(True)
        hw_layout.addWidget(self.hw_info)
        hw_group.setLayout(hw_layout)
        layout.addWidget(hw_group)
        
        metrics_group = QGroupBox("Подробные метрики производительности")
        metrics_group.setFont(font)
        metrics_layout = QVBoxLayout()
        self.metrics_info = QTextEdit()
        self.metrics_info.setFont(QFont("Consolas", 9))
        self.metrics_info.setReadOnly(True)
        metrics_layout.addWidget(self.metrics_info)
        metrics_group.setLayout(metrics_layout)
        layout.addWidget(metrics_group)
        
        self.setLayout(layout)
    
    def update_info(self, host_info):
        basic = host_info.get("basic", {})
        self.basic_info.setText(
            f"Hostname: {basic.get('hostname', 'N/A')}\n"
            f"IP Address: {basic.get('ip_address', 'N/A')}\n"
            f"MAC Address: {basic.get('mac_address', 'N/A')}\n"
            f"OS Version: {basic.get('os_version', 'N/A')}\n"
            f"Computer ID: {basic.get('computer_id', 'N/A')}"
        )
        
        hw = host_info.get("hardware", {})
        self.hw_info.setText(
            f"CPU Model: {hw.get('cpu_model', 'N/A')}\n"
            f"CPU Cores: {hw.get('cpu_cores', 0)} (Physical: {hw.get('cpu_physical_cores', 0)})\n"
            f"RAM Total: {hw.get('ram_total', 0)} GB\n"
            f"Storage Total: {hw.get('storage_total', 0)} GB\n"
            f"GPU Model: {hw.get('gpu_model', 'N/A')}"
        )
        
        metrics = host_info.get("metrics", {})
        self.metrics_info.setText(
            f"CPU Usage: {metrics.get('cpu_usage', 0)}%\n"
            f"RAM Usage: {metrics.get('ram_usage', 0)}% ({metrics.get('ram_used_gb', 0)} GB / {metrics.get('ram_total_gb', 0)} GB)\n"
            f"Disk Usage: {metrics.get('disk_usage', 0)}% ({metrics.get('disk_used_gb', 0)} GB / {metrics.get('disk_total_gb', 0)} GB)\n"
            f"Timestamp: {metrics.get('timestamp', 'N/A')}"
        )
        
        if host_info.get("last_update"):
            self.update_time_label.setText(f"Последнее обновление: {host_info['last_update']}")


class RemoteScreenWidget(QLabel):
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
    
    def update_image_position(self):
        pixmap = self.pixmap()
        if pixmap:
            self.image_offset_x = (self.width() - pixmap.width()) // 2
            self.image_offset_y = (self.height() - pixmap.height()) // 2
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_position()
    
    def client_to_host_coords(self, client_x, client_y):
        if (self.host_screen_width and self.host_screen_height and 
            self.display_image_width and self.display_image_height):
            
            host_x = int(client_x * self.scale_x)
            host_y = int(client_y * self.scale_y)
            
            host_x = max(0, min(host_x, self.host_screen_width - 1))
            host_y = max(0, min(host_y, self.host_screen_height - 1))
            
            return host_x, host_y
        return client_x, client_y
    
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


class RemoteClientThread(QThread):
    status_updated = pyqtSignal(str, str)
    image_received = pyqtSignal(object)
    system_info_received = pyqtSignal(dict)
    connection_lost = pyqtSignal()
    
    def __init__(self, relay_server, computer_id, client_id, update_interval):
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
                    
                    # Регистрация клиента с computer_id
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
                                
                                self.host_screen_width, self.host_screen_height = img.size
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
                # Используем computer_id для идентификации
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


class RemoteAccessClientWindow(QMainWindow):
    key_pressed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client_thread = None
        self.host_info = {"basic": {}, "hardware": {}, "metrics": {}, "last_update": None}
        self.frame_count = 0
        self.last_fps_update = time.time()
        self.remote_screen_active = False
        self.remote_window = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Удалённый доступ - Клиент")
        self.setGeometry(100, 100, 1200, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        settings_frame = QFrame()
        settings_frame.setFrameStyle(QFrame.Shape.Box)
        settings_frame.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        
        settings_layout = QGridLayout(settings_frame)
        
        settings_layout.addWidget(QLabel("Сервер:"), 0, 0)
        self.server_edit = QLineEdit("ws://localhost:9001")
        settings_layout.addWidget(self.server_edit, 0, 1)
        
        settings_layout.addWidget(QLabel("Computer ID:"), 1, 0)
        self.computer_id_edit = QLineEdit("")
        self.computer_id_edit.setPlaceholderText("Введите computer_id компьютера")
        settings_layout.addWidget(self.computer_id_edit, 1, 1)
        
        settings_layout.addWidget(QLabel("ID клиента:"), 2, 0)
        self.client_id_edit = QLineEdit("CLIENT_001")
        settings_layout.addWidget(self.client_id_edit, 2, 1)
        
        # Добавляем информационную метку
        info_label = QLabel("ℹ️ Computer ID можно найти в логах хоста после регистрации")
        info_label.setStyleSheet("color: gray; font-size: 10px; padding: 5px;")
        info_label.setWordWrap(True)
        settings_layout.addWidget(info_label, 3, 0, 1, 2)
        
        button_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("ПОДКЛЮЧИТЬСЯ")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 10px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.connect_btn.clicked.connect(self.start_client)
        button_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("ОТКЛЮЧИТЬСЯ")
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 10px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.disconnect_btn.clicked.connect(self.stop_client)
        button_layout.addWidget(self.disconnect_btn)
        
        settings_layout.addLayout(button_layout, 4, 0, 1, 2)
        main_layout.addWidget(settings_frame)
        
        self.status_label = QLabel("Отключено")
        self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        main_layout.addWidget(self.status_label)
        
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.metrics_table = MetricsTableWidget()
        self.metrics_table.refresh_btn.clicked.connect(self.request_system_info)
        left_layout.addWidget(self.metrics_table)
        
        self.remote_screen_btn = QPushButton("ОТКРЫТЬ УДАЛЕННЫЙ ЭКРАН")
        self.remote_screen_btn.setEnabled(False)
        self.remote_screen_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.remote_screen_btn.clicked.connect(self.open_remote_screen)
        left_layout.addWidget(self.remote_screen_btn)
        
        self.tab_widget = QTabWidget()
        
        self.info_display = SystemInfoDisplay()
        self.info_display.refresh_btn.clicked.connect(self.request_system_info)
        self.tab_widget.addTab(self.info_display, "Подробная информация")
        
        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(self.tab_widget)
        content_splitter.setSizes([400, 800])
        
        main_layout.addWidget(content_splitter)
        
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)
        
        self.metrics_update_timer = QTimer()
        self.metrics_update_timer.timeout.connect(self.request_system_info)
        self.metrics_update_timer.start(60000)
    
    def start_client(self):
        if not self.server_edit.text().startswith('ws://'):
            QMessageBox.warning(self, "Ошибка", "Сервер должен начинаться с ws://")
            return
        if not self.computer_id_edit.text():
            QMessageBox.warning(self, "Ошибка", "Введите Computer ID")
            return
        
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.remote_screen_btn.setEnabled(True)
        self.metrics_table.refresh_btn.setEnabled(True)
        self.info_display.refresh_btn.setEnabled(True)
        self.status_label.setText("Подключение...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold; padding: 5px;")
        
        self.client_thread = RemoteClientThread(
            relay_server=self.server_edit.text(),
            computer_id=self.computer_id_edit.text(),
            client_id=self.client_id_edit.text(),
            update_interval=0.033
        )
        
        self.client_thread.status_updated.connect(self.on_status_updated)
        self.client_thread.image_received.connect(self.on_image_received)
        self.client_thread.system_info_received.connect(self.on_system_info_received)
        self.client_thread.connection_lost.connect(self.on_connection_lost)
        
        self.client_thread.start()
    
    def stop_client(self):
        if self.remote_window:
            self.stop_stream()
            self.remote_window.close()
            self.remote_window = None
        
        if self.client_thread:
            self.client_thread.stop()
            self.client_thread = None
        
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.remote_screen_btn.setEnabled(False)
        self.metrics_table.refresh_btn.setEnabled(False)
        self.info_display.refresh_btn.setEnabled(False)
        self.status_label.setText("Отключено")
        self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        
        self.fps_timer.stop()
        self.frame_count = 0
    
    def on_status_updated(self, message, msg_type):
        colors = {"info": "black", "success": "green", "error": "red", "warning": "orange"}
        color = colors.get(msg_type, "black")
        
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 5px;")
    
    def on_image_received(self, img):
        if self.remote_window and self.remote_window.isVisible():
            self.remote_window.update_image(img)
            self.frame_count += 1
    
    def on_system_info_received(self, system_data):
        # Добавляем computer_id в информацию о хосте
        if "computer_id" not in system_data:
            system_data["computer_id"] = self.computer_id_edit.text()
            
        self.host_info = {
            "basic": system_data.get("basic", {}),
            "hardware": system_data.get("hardware", {}),
            "metrics": system_data.get("metrics", {}),
            "last_update": system_data.get("timestamp", datetime.now().isoformat())
        }
        
        # Добавляем computer_id в basic информацию
        self.host_info["basic"]["computer_id"] = system_data.get("computer_id", self.computer_id_edit.text())
        
        self.metrics_table.update_table(system_data.get("metrics", {}))
        if system_data.get("timestamp"):
            try:
                formatted_time = datetime.fromisoformat(system_data['timestamp']).strftime("%H:%M:%S")
                self.metrics_table.update_time_label.setText(f"Последнее обновление: {formatted_time}")
            except:
                self.metrics_table.update_time_label.setText(f"Последнее обновление: {system_data['timestamp']}")
        
        self.info_display.update_info(self.host_info)
        
        self.metrics_table.refresh_btn.setEnabled(True)
        self.metrics_table.refresh_btn.setText("ОБНОВИТЬ МЕТРИКИ")
        self.info_display.refresh_btn.setEnabled(True)
        self.info_display.refresh_btn.setText("ОБНОВИТЬ ИНФОРМАЦИЮ")
    
    def on_connection_lost(self):
        if self.remote_window:
            self.remote_window.clear_screen()
    
    def update_fps(self):
        if self.remote_window and self.remote_window.isVisible():
            self.remote_window.update_fps(self.frame_count)
        self.frame_count = 0
    
    def start_stream(self):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.queue_command({
                "type": "start_stream",
                "data": {}
            })

    def stop_stream(self):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.queue_command({
                "type": "stop_stream",
                "data": {}
            })
    
    def open_remote_screen(self):
        if not self.client_thread or not self.client_thread.is_connected:
            QMessageBox.warning(self, "Ошибка", "Сначала подключитесь к компьютеру")
            return
        
        self.start_stream()
        QTimer.singleShot(500, self._create_remote_window)

    def _create_remote_window(self):
        if not self.remote_window:
            self.remote_window = RemoteScreenWindow(self.client_thread)
            self.remote_window.key_pressed.connect(self.on_key_press)
            self.remote_window.closed.connect(self.on_remote_window_closed)
        
        self.remote_window.show()
        self.remote_window.raise_()
        self.remote_window.activateWindow()
        self.fps_timer.start(1000)
        
        QTimer.singleShot(1000, self.start_stream)
    
    def on_remote_window_closed(self):
        self.stop_stream()
        self.remote_window = None
        self.fps_timer.stop()
        self.frame_count = 0
    
    def on_mouse_move(self, client_x, client_y, host_x, host_y):
        if self.client_thread and self.client_thread.is_connected and self.remote_window:
            self.client_thread.queue_command({
                "type": "mouse_move",
                "data": {"x": host_x, "y": host_y}
            })
    
    def on_mouse_click(self, button, host_x, host_y):
        if self.client_thread and self.client_thread.is_connected and self.remote_window:
            self.client_thread.queue_command({
                "type": "mouse_click",
                "data": {"button": button, "x": host_x, "y": host_y}
            })
    
    def on_mouse_wheel(self, delta):
        if self.client_thread and self.client_thread.is_connected and self.remote_window:
            self.client_thread.queue_command({
                "type": "mouse_wheel",
                "data": {"delta": delta}
            })
    
    def on_key_press(self, text):
        if self.client_thread and self.client_thread.is_connected and self.remote_window:
            self.client_thread.queue_command({
                "type": "keyboard_input",
                "data": {"text": text}
            })
    
    def request_system_info(self):
        if self.client_thread and self.client_thread.is_connected:
            self.metrics_table.refresh_btn.setEnabled(False)
            self.metrics_table.refresh_btn.setText("ОБНОВЛЕНИЕ...")
            self.info_display.refresh_btn.setEnabled(False)
            self.info_display.refresh_btn.setText("ОБНОВЛЕНИЕ...")
            
            self.client_thread.request_system_info()
    
    def closeEvent(self, event):
        self.stop_client()
        event.accept()


class RemoteScreenWindow(QMainWindow):
    key_pressed = pyqtSignal(str)
    closed = pyqtSignal()
    
    def __init__(self, client_thread):
        super().__init__()
        self.client_thread = client_thread
        self.frame_count = 0
        self.original_width = 0
        self.original_height = 0
        self.display_width = 0
        self.display_height = 0
        self.init_ui()
        
        self.screen_widget.mouse_moved.connect(self.on_mouse_move)
        self.screen_widget.mouse_clicked.connect(self.on_mouse_click)
        self.screen_widget.mouse_wheeled.connect(self.on_mouse_wheel)
        self.screen_widget.key_pressed.connect(self.on_key_press)
    
    def init_ui(self):
        self.setWindowTitle("Удаленный экран")
        self.setGeometry(200, 200, 1280, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        status_bar = QFrame()
        status_bar.setStyleSheet("background-color: #2c3e50;")
        status_bar.setFixedHeight(25)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(5, 0, 5, 0)
        
        self.status_label = QLabel("Удаленный экран")
        self.status_label.setStyleSheet("color: white; font-size: 11px;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("color: white; font-size: 11px;")
        status_layout.addWidget(self.fps_label)
        
        self.resolution_label = QLabel("")
        self.resolution_label.setStyleSheet("color: white; font-size: 11px;")
        status_layout.addWidget(self.resolution_label)
        
        layout.addWidget(status_bar)
        
        self.screen_widget = RemoteScreenWidget()
        self.screen_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.screen_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
            
            self.screen_widget.set_display_info(
                self.original_width, 
                self.original_height,
                self.display_width, 
                self.display_height
            )
            
            img_byte_array = BytesIO()
            img_resized.save(img_byte_array, format='PNG')
            qimage = QImage.fromData(img_byte_array.getvalue())
            pixmap = QPixmap.fromImage(qimage)
            
            self.screen_widget.setPixmap(pixmap)
            self.screen_widget.set_screen_size(img.width, img.height)
            self.screen_widget.update_image_position()
            self.frame_count += 1
            
            scale_percent = int((new_width / img.width) * 100)
            self.resolution_label.setText(
                f"Сервер: {img.width}x{img.height} | "
                f"Экран: {new_width}x{new_height} | "
                f"Масштаб: {scale_percent}%"
            )
    
    def update_fps(self, fps):
        self.fps_label.setText(f"FPS: {fps}")
    
    def clear_screen(self):
        self.screen_widget.clear()
        self.status_label.setText("Соединение потеряно")
        self.status_label.setStyleSheet("color: red; font-size: 11px;")
    
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
        self.closed.emit()
        event.accept()


class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client_window = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Удалённый доступ - Настройки")
        self.setGeometry(300, 300, 400, 250)
        self.setStyleSheet("background-color: #f0f0f0;")
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        header = QLabel("УДАЛЕННЫЙ ДОСТУП")
        header.setStyleSheet("""
            QLabel {
                background-color: #2c3e50;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
            }
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        start_btn = QPushButton("ЗАПУСТИТЬ КЛИЕНТ")
        start_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        start_btn.clicked.connect(self.start_client)
        layout.addWidget(start_btn)
        
        self.status_label = QLabel("Готов к запуску")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray; padding: 10px;")
        layout.addWidget(self.status_label)
    
    def start_client(self):
        self.client_window = RemoteAccessClientWindow()
        self.client_window.show()
        self.status_label.setText("Клиент запущен")
        self.status_label.setStyleSheet("color: green; padding: 10px;")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = SettingsWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()