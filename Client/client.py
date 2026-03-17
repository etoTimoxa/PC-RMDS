import sys
import asyncio
import websockets
import json
import base64
from io import BytesIO
import threading
import time
import queue
from datetime import datetime
import os
import PyQt5

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTabWidget, QTextEdit, QFrame, QMessageBox,
                            QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QPixmap, QImage, QFont, QColor, QPalette

from PIL import Image, ImageTk


class SystemInfoDisplay(QWidget):
    """Виджет для отображения информации о системе"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Кнопка обновления
        top_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 ОБНОВИТЬ ИНФОРМАЦИЮ")
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
        
        # Основная информация
        basic_group = QGroupBox("Основная информация")
        basic_group.setFont(QFont("Arial", 10, QFont.Bold))
        basic_layout = QVBoxLayout()
        self.basic_info = QTextEdit()
        self.basic_info.setFont(QFont("Consolas", 9))
        self.basic_info.setMaximumHeight(100)
        self.basic_info.setReadOnly(True)
        basic_layout.addWidget(self.basic_info)
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # Конфигурация оборудования
        hw_group = QGroupBox("Конфигурация оборудования")
        hw_group.setFont(QFont("Arial", 10, QFont.Bold))
        hw_layout = QVBoxLayout()
        self.hw_info = QTextEdit()
        self.hw_info.setFont(QFont("Consolas", 9))
        self.hw_info.setMaximumHeight(120)
        self.hw_info.setReadOnly(True)
        hw_layout.addWidget(self.hw_info)
        hw_group.setLayout(hw_layout)
        layout.addWidget(hw_group)
        
        # Метрики производительности
        metrics_group = QGroupBox("Метрики производительности")
        metrics_group.setFont(QFont("Arial", 10, QFont.Bold))
        metrics_layout = QVBoxLayout()
        self.metrics_info = QTextEdit()
        self.metrics_info.setFont(QFont("Consolas", 9))
        self.metrics_info.setReadOnly(True)
        metrics_layout.addWidget(self.metrics_info)
        metrics_group.setLayout(metrics_layout)
        layout.addWidget(metrics_group)
        
        # События и предупреждения
        events_group = QGroupBox("События и предупреждения")
        events_group.setFont(QFont("Arial", 10, QFont.Bold))
        events_layout = QVBoxLayout()
        self.events_info = QTextEdit()
        self.events_info.setFont(QFont("Consolas", 9))
        self.events_info.setMaximumHeight(80)
        self.events_info.setReadOnly(True)
        events_layout.addWidget(self.events_info)
        events_group.setLayout(events_layout)
        layout.addWidget(events_group)
        
        self.setLayout(layout)
    
    def update_info(self, host_info):
        """Обновляет отображение информации"""
        basic = host_info.get("basic", {})
        self.basic_info.setText(
            f"Hostname: {basic.get('hostname', 'N/A')}\n"
            f"IP Address: {basic.get('ip_address', 'N/A')}\n"
            f"MAC Address: {basic.get('mac_address', 'N/A')}\n"
            f"OS Version: {basic.get('os_version', 'N/A')}"
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
        
        events = metrics.get('events', [])
        if events:
            events_text = "\n".join([f"⚠️ {event.get('description', '')}" for event in events])
            self.events_info.setText(events_text)
        else:
            self.events_info.setText("✅ Нет активных предупреждений")
        
        if host_info.get("last_update"):
            self.update_time_label.setText(f"Последнее обновление: {host_info['last_update']}")


class RemoteScreenWidget(QLabel):
    """Виджет для отображения удаленного экрана"""
    
    mouse_moved = pyqtSignal(int, int)
    mouse_clicked = pyqtSignal(str)
    mouse_wheeled = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.host_screen_width = None
        self.host_screen_height = None
        self.setFocusPolicy(Qt.StrongFocus)
    
    def mouseMoveEvent(self, event):
        if self.host_screen_width and self.host_screen_height:
            scale_x = self.host_screen_width / max(self.width(), 1)
            scale_y = self.host_screen_height / max(self.height(), 1)
            x = int(event.x() * scale_x)
            y = int(event.y() * scale_y)
            self.mouse_moved.emit(x, y)
    
    def mousePressEvent(self, event):
        button = "left" if event.button() == Qt.LeftButton else "right" if event.button() == Qt.RightButton else "middle"
        self.mouse_clicked.emit(button)
    
    def wheelEvent(self, event):
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.mouse_wheeled.emit(delta)
    
    def keyPressEvent(self, event):
        if event.text():
            self.parent().key_pressed.emit(event.text())
    
    def set_screen_size(self, width, height):
        self.host_screen_width = width
        self.host_screen_height = height


class RemoteClientThread(QThread):
    """Поток для работы с WebSocket соединением"""
    
    status_updated = pyqtSignal(str, str)
    image_received = pyqtSignal(object)
    system_info_received = pyqtSignal(dict)
    connection_lost = pyqtSignal()
    
    def __init__(self, relay_server, host_id, client_id, update_interval):
        super().__init__()
        self.relay_server = relay_server
        self.host_id = host_id
        self.client_id = client_id
        self.update_interval = update_interval
        self.ws = None
        self.is_running = True
        self.is_connected = False
        self.command_queue = queue.Queue()
        self.host_screen_width = None
        self.host_screen_height = None
    
    def run(self):
        asyncio.run(self.client_loop())
    
    async def client_loop(self):
        reconnect_delay = 2
        while self.is_running:
            try:
                self.status_updated.emit("Подключение...", "warning")
                
                async with websockets.connect(self.relay_server) as websocket:
                    self.ws = websocket
                    await self.ws.send(json.dumps({
                        "type": "register_client",
                        "data": {"client_id": self.client_id, "host_id": self.host_id},
                        "host_id": self.host_id,
                        "client_id": self.client_id
                    }))
                    
                    self.is_connected = True
                    self.status_updated.emit("Подключено", "success")
                    
                    last_update = 0
                    
                    async for msg in self.ws:
                        data = json.loads(msg)
                        
                        if data.get("type") == "screenshot":
                            now = time.time()
                            if now - last_update >= self.update_interval:
                                last_update = now
                                
                                img_data = base64.b64decode(data["data"])
                                img = Image.open(BytesIO(img_data))
                                
                                self.host_screen_width, self.host_screen_height = img.size
                                self.image_received.emit(img)
                        
                        elif data.get("type") == "system_info":
                            system_data = data.get("data", {})
                            self.system_info_received.emit(system_data)
                        
                        # Обработка команд из очереди
                        while not self.command_queue.empty():
                            try:
                                cmd = self.command_queue.get_nowait()
                                await self.send_command(cmd)
                            except:
                                pass
                            
            except Exception as e:
                self.status_updated.emit(f"Ошибка: {str(e)}", "error")
            
            self.is_connected = False
            self.status_updated.emit("Отключено", "error")
            self.connection_lost.emit()
            await asyncio.sleep(reconnect_delay)
    
    async def send_command(self, command):
        if self.ws and self.is_connected:
            try:
                message = {
                    "type": command.get("type", "command"),
                    "data": command.get("data", {}),
                    "host_id": self.host_id,
                    "client_id": self.client_id
                }
                await self.ws.send(json.dumps(message))
            except:
                pass
    
    def queue_command(self, command):
        self.command_queue.put(command)
    
    def request_system_info(self):
        if self.is_connected:
            self.queue_command({"type": "request_system_info", "data": {}})
    
    def stop(self):
        self.is_running = False
        self.is_connected = False


class RemoteAccessClientWindow(QMainWindow):
    """Главное окно клиента"""
    
    key_pressed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client_thread = None
        self.host_info = {"basic": {}, "hardware": {}, "metrics": {}, "last_update": None}
        self.frame_count = 0
        self.last_fps_update = time.time()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Удалённый доступ - Клиент")
        self.setGeometry(100, 100, 1000, 700)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QVBoxLayout(central_widget)
        
        # Верхняя панель с настройками
        settings_frame = QFrame()
        settings_frame.setFrameStyle(QFrame.Box)
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
        self.server_edit = QLineEdit("ws://130.49.149.152:9001")
        settings_layout.addWidget(self.server_edit, 0, 1)
        
        settings_layout.addWidget(QLabel("ID хоста:"), 1, 0)
        self.host_id_edit = QLineEdit("PC_HOME")
        settings_layout.addWidget(self.host_id_edit, 1, 1)
        
        settings_layout.addWidget(QLabel("ID клиента:"), 2, 0)
        self.client_id_edit = QLineEdit("CLIENT")
        settings_layout.addWidget(self.client_id_edit, 2, 1)
        
        # Кнопки управления
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
        
        settings_layout.addLayout(button_layout, 3, 0, 1, 2)
        main_layout.addWidget(settings_frame)
        
        # Статус
        self.status_label = QLabel("Отключено")
        self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        main_layout.addWidget(self.status_label)
        
        # Вкладки
        self.tab_widget = QTabWidget()
        
        # Вкладка удаленного экрана
        screen_tab = QWidget()
        screen_layout = QVBoxLayout(screen_tab)
        
        # Статус экрана
        screen_status = QHBoxLayout()
        self.screen_status = QLabel("Не подключено")
        self.screen_status.setStyleSheet("color: red;")
        screen_status.addWidget(self.screen_status)
        
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("color: white;")
        screen_status.addWidget(self.fps_label)
        
        status_bar = QFrame()
        status_bar.setStyleSheet("background-color: #2c3e50; padding: 5px;")
        status_bar.setLayout(screen_status)
        status_bar.setFixedHeight(30)
        screen_layout.addWidget(status_bar)
        
        # Виджет экрана
        self.screen_widget = RemoteScreenWidget()
        self.screen_widget.mouse_moved.connect(self.on_mouse_move)
        self.screen_widget.mouse_clicked.connect(self.on_mouse_click)
        self.screen_widget.mouse_wheeled.connect(self.on_mouse_wheel)
        self.key_pressed.connect(self.on_key_press)
        screen_layout.addWidget(self.screen_widget)
        
        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        close_btn.clicked.connect(self.close)
        screen_layout.addWidget(close_btn)
        
        self.tab_widget.addTab(screen_tab, "Удаленный экран")
        
        # Вкладка информации
        self.info_display = SystemInfoDisplay()
        self.info_display.refresh_btn.clicked.connect(self.request_system_info)
        self.tab_widget.addTab(self.info_display, "Информация о хосте")
        
        main_layout.addWidget(self.tab_widget)
        
        # Таймер для FPS
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)
        
        # Таймер для обработки очереди команд
        self.command_timer = QTimer()
        self.command_timer.timeout.connect(self.process_commands)
        self.command_timer.start(100)
    
    def start_client(self):
        if not self.server_edit.text().startswith('ws://'):
            QMessageBox.warning(self, "Ошибка", "Сервер должен начинаться с ws://")
            return
        if not self.host_id_edit.text():
            QMessageBox.warning(self, "Ошибка", "Введите ID хоста")
            return
        
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.status_label.setText("Подключение...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold; padding: 5px;")
        
        self.client_thread = RemoteClientThread(
            relay_server=self.server_edit.text(),
            host_id=self.host_id_edit.text(),
            client_id=self.client_id_edit.text(),
            update_interval=0.033
        )
        
        self.client_thread.status_updated.connect(self.on_status_updated)
        self.client_thread.image_received.connect(self.on_image_received)
        self.client_thread.system_info_received.connect(self.on_system_info_received)
        self.client_thread.connection_lost.connect(self.on_connection_lost)
        
        self.client_thread.start()
    
    def stop_client(self):
        if self.client_thread:
            self.client_thread.stop()
            self.client_thread = None
        
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.status_label.setText("Отключено")
        self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        self.screen_status.setText("Отключено")
        self.screen_status.setStyleSheet("color: red;")
    
    def on_status_updated(self, message, msg_type):
        colors = {"info": "black", "success": "green", "error": "red", "warning": "orange"}
        color = colors.get(msg_type, "black")
        
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 5px;")
        self.screen_status.setText(message)
        self.screen_status.setStyleSheet(f"color: {color};")
        
        if "Подключено" in message:
            self.info_display.refresh_btn.setEnabled(True)
        else:
            self.info_display.refresh_btn.setEnabled(False)
    
    def on_image_received(self, img):
        # Масштабирование изображения
        win_width = max(self.screen_widget.width(), 1)
        win_height = max(self.screen_widget.height(), 1)
        
        img_ratio = img.width / img.height
        win_ratio = win_width / win_height
        
        if img_ratio > win_ratio:
            new_width = win_width
            new_height = int(win_width / img_ratio)
        else:
            new_height = win_height
            new_width = int(win_height * img_ratio)
        
        if new_width > 0 and new_height > 0:
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Конвертация в QPixmap
            img_byte_array = BytesIO()
            img_resized.save(img_byte_array, format='PNG')
            qimage = QImage.fromData(img_byte_array.getvalue())
            pixmap = QPixmap.fromImage(qimage)
            
            self.screen_widget.setPixmap(pixmap)
            self.screen_widget.set_screen_size(img.width, img.height)
            self.frame_count += 1
    
    def on_system_info_received(self, system_data):
        self.host_info = {
            "basic": system_data.get("basic", {}),
            "hardware": system_data.get("hardware", {}),
            "metrics": system_data.get("metrics", {}),
            "last_update": system_data.get("timestamp", datetime.now().isoformat())
        }
        self.info_display.update_info(self.host_info)
    
    def on_connection_lost(self):
        self.screen_widget.clear()
    
    def update_fps(self):
        self.fps_label.setText(f"FPS: {self.frame_count}")
        self.frame_count = 0
    
    def on_mouse_move(self, x, y):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.queue_command({
                "type": "mouse_move",
                "data": {"action": "mouse_move", "x": x, "y": y}
            })
    
    def on_mouse_click(self, button):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.queue_command({
                "type": "mouse_click",
                "data": {"action": "mouse_click", "button": button}
            })
    
    def on_mouse_wheel(self, delta):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.queue_command({
                "type": "mouse_wheel",
                "data": {"action": "mouse_wheel", "delta": delta}
            })
    
    def on_key_press(self, text):
        if self.client_thread and self.client_thread.is_connected:
            self.client_thread.queue_command({
                "type": "command",
                "data": {"action": "text_input", "text": text}
            })
    
    def request_system_info(self):
        if self.client_thread and self.client_thread.is_connected:
            self.info_display.refresh_btn.setEnabled(False)
            self.info_display.refresh_btn.setText("⏳ ОБНОВЛЕНИЕ...")
            self.client_thread.request_system_info()
            QTimer.singleShot(2000, self.restore_refresh_button)
    
    def restore_refresh_button(self):
        self.info_display.refresh_btn.setEnabled(True)
        self.info_display.refresh_btn.setText("🔄 ОБНОВИТЬ ИНФОРМАЦИЮ")
    
    def process_commands(self):
        pass  # Команды обрабатываются в потоке
    
    def closeEvent(self, event):
        self.stop_client()
        event.accept()


class SettingsWindow(QMainWindow):
    """Окно настроек (для совместимости с оригинальной структурой)"""
    
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
        
        # Заголовок
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
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Кнопка запуска клиента
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
        
        # Статус
        self.status_label = QLabel("Готов к запуску")
        self.status_label.setAlignment(Qt.AlignCenter)
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
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins')
    main()