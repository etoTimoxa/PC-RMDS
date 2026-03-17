import sys
import asyncio
import websockets
import json
import mss
from io import BytesIO
from PIL import Image
import base64
import threading
import time
import platform
import psutil
import socket
import os
import PyQt5
from datetime import datetime



from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTextEdit, QFrame, QMessageBox, QGroupBox,
                            QGridLayout)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCursor

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController


class SystemInfoCollector:
    """Сбор информации о системе"""
    
    @staticmethod
    def get_basic_info():
        try:
            hostname = socket.gethostname()
            ip_address = "Unknown"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip_address = s.getsockname()[0]
                s.close()
            except:
                ip_address = socket.gethostbyname(hostname)
            
            mac_address = "Unknown"
            try:
                import uuid
                mac = uuid.getnode()
                mac_address = ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))
            except:
                pass
            
            return {
                "hostname": hostname,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "os_version": f"{platform.system()} {platform.release()}",
                "last_online": datetime.now().isoformat(),
                "is_active": True
            }
        except:
            return {}
    
    @staticmethod
    def get_hardware_config():
        try:
            cpu_model = platform.processor() or "Unknown"
            cpu_cores = psutil.cpu_count(logical=True)
            cpu_physical_cores = psutil.cpu_count(logical=False)
            ram = psutil.virtual_memory()
            ram_total = ram.total / (1024**3)
            disk = psutil.disk_usage('/')
            storage_total = disk.total / (1024**3)
            gpu_model = "Unknown"
            
            return {
                "cpu_model": cpu_model,
                "cpu_cores": cpu_cores,
                "cpu_physical_cores": cpu_physical_cores,
                "ram_total": round(ram_total, 2),
                "storage_total": round(storage_total, 2),
                "gpu_model": gpu_model
            }
        except:
            return {}
    
    @staticmethod
    def get_performance_metrics():
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            ram_usage = ram.percent
            ram_used = ram.used / (1024**3)
            ram_total = ram.total / (1024**3)
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            disk_used = disk.used / (1024**3)
            disk_total = disk.total / (1024**3)
            
            events = []
            if cpu_usage > 90:
                events.append({"event_type": "warning", "event_source": "cpu", 
                             "description": f"Высокая загрузка CPU: {cpu_usage}%", 
                             "severity_level": "medium"})
            if ram_usage > 90:
                events.append({"event_type": "warning", "event_source": "memory", 
                             "description": f"Высокое использование RAM: {ram_usage}%", 
                             "severity_level": "medium"})
            if disk_usage > 90:
                events.append({"event_type": "warning", "event_source": "disk", 
                             "description": f"Мало места на диске: {disk_usage}% использовано", 
                             "severity_level": "medium"})
            
            return {
                "cpu_usage": cpu_usage,
                "ram_usage": ram_usage,
                "ram_used_gb": round(ram_used, 2),
                "ram_total_gb": round(ram_total, 2),
                "disk_usage": disk_usage,
                "disk_used_gb": round(disk_used, 2),
                "disk_total_gb": round(disk_total, 2),
                "events": events,
                "timestamp": datetime.now().isoformat()
            }
        except:
            return {}


class RemoteHostThread(QThread):
    """Поток для работы с WebSocket соединением"""
    
    log_message = pyqtSignal(str)
    status_changed = pyqtSignal(bool, int)
    
    def __init__(self, relay_server, host_id, screenshot_interval):
        super().__init__()
        self.relay_server = relay_server
        self.host_id = host_id
        self.screenshot_interval = screenshot_interval
        self.is_running = True
        self.is_connected = False
        self.connected_clients = 0
        self.ws = None
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        try:
            import pyautogui
            self.screen_width, self.screen_height = pyautogui.size()
        except:
            self.screen_width, self.screen_height = 1920, 1080
        
        self.KEY_MAPPING = {
            'enter': Key.enter, 'space': Key.space, 'tab': Key.tab,
            'backspace': Key.backspace, 'escape': Key.esc, 'esc': Key.esc,
            'shift': Key.shift, 'ctrl': Key.ctrl, 'alt': Key.alt,
            'up': Key.up, 'down': Key.down, 'left': Key.left, 'right': Key.right,
            'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3, 'f4': Key.f4,
            'f5': Key.f5, 'f6': Key.f6, 'f7': Key.f7, 'f8': Key.f8,
            'f9': Key.f9, 'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
            'delete': Key.delete, 'home': Key.home, 'end': Key.end,
            'page_up': Key.page_up, 'page_down': Key.page_down,
        }
    
    def run(self):
        asyncio.run(self.host_main())
    
    async def host_main(self):
        reconnect_delay = 2
        while self.is_running:
            try:
                async with websockets.connect(self.relay_server) as ws:
                    self.ws = ws
                    await ws.send(json.dumps({
                        "type": "register_host",
                        "data": {"host_id": self.host_id},
                        "host_id": self.host_id
                    }))
                    
                    self.is_connected = True
                    self.status_changed.emit(True, self.connected_clients)
                    self.log_message.emit("✅ Подключен к серверу")
                    
                    # Создаем задачи
                    send_task = asyncio.create_task(self.send_loop(ws))
                    info_task = asyncio.create_task(self.info_loop(ws))
                    receive_task = asyncio.create_task(self.receive_commands(ws))
                    
                    # Ожидаем завершения любой из задач
                    await asyncio.wait([send_task, info_task, receive_task], 
                                     return_when=asyncio.FIRST_COMPLETED)
                    
                    # Отменяем все задачи
                    for task in [send_task, info_task, receive_task]:
                        task.cancel()
                    
            except Exception as e:
                self.log_message.emit(f"❌ Ошибка подключения: {e}")
            
            self.is_connected = False
            self.connected_clients = 0
            self.status_changed.emit(False, 0)
            
            if self.is_running:
                self.log_message.emit(f"🔄 Переподключение через {reconnect_delay} сек...")
                await asyncio.sleep(reconnect_delay)
    
    async def send_system_info(self, ws):
        try:
            system_info = {
                "basic": SystemInfoCollector.get_basic_info(),
                "hardware": SystemInfoCollector.get_hardware_config(),
                "metrics": SystemInfoCollector.get_performance_metrics(),
                "timestamp": datetime.now().isoformat()
            }
            
            await ws.send(json.dumps({
                "type": "system_info",
                "data": system_info,
                "host_id": self.host_id
            }))
            self.log_message.emit("📊 Информация о системе отправлена")
            return True
        except Exception as e:
            self.log_message.emit(f"⚠️ Ошибка отправки информации: {e}")
            return False
    
    async def info_loop(self, ws):
        """Периодическая отправка информации о системе"""
        await self.send_system_info(ws)
        last_sent = time.time()
        
        while self.is_running and self.is_connected:
            try:
                # Отправляем информацию каждый час
                if time.time() - last_sent >= 3600:
                    await self.send_system_info(ws)
                    last_sent = time.time()
                await asyncio.sleep(60)
            except Exception as e:
                self.log_message.emit(f"⚠️ Ошибка в info_loop: {e}")
                break
    
    async def send_screenshot(self, ws):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Основной монитор
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                
                # Сжимаем изображение
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=70, optimize=True)
                img_b64 = base64.b64encode(buffer.getvalue()).decode()
                
                await ws.send(json.dumps({
                    "type": "screenshot",
                    "data": img_b64,
                    "host_id": self.host_id
                }))
                return True
        except Exception as e:
            self.log_message.emit(f"⚠️ Ошибка создания скриншота: {e}")
            return False
    
    async def send_loop(self, ws):
        """Цикл отправки скриншотов"""
        while self.is_running and self.is_connected:
            try:
                await self.send_screenshot(ws)
                await asyncio.sleep(self.screenshot_interval)
            except Exception as e:
                self.log_message.emit(f"⚠️ Ошибка в send_loop: {e}")
                break
    
    async def receive_commands(self, ws):
        """Получение и обработка команд от клиента"""
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                cmd_data = data.get("data", {})
                
                if cmd_type == "register_client":
                    self.connected_clients += 1
                    self.status_changed.emit(True, self.connected_clients)
                    self.log_message.emit(f"👤 Клиент подключен (всего: {self.connected_clients})")
                    await self.send_system_info(ws)
                
                elif cmd_type == "request_system_info":
                    self.log_message.emit("📋 Запрос информации о системе")
                    await self.send_system_info(ws)
                
                elif cmd_type in ["mouse_move", "mouse_click", "mouse_wheel", "command"]:
                    await self.handle_command(cmd_data)
                    
        except Exception as e:
            self.log_message.emit(f"⚠️ Ошибка в receive_commands: {e}")
    
    async def handle_command(self, command):
        """Обработка команд управления"""
        try:
            action = command.get("action")
            
            if action == "mouse_move":
                x, y = command.get("x"), command.get("y")
                if x is not None and y is not None:
                    self.mouse.position = (x, y)
                    
            elif action == "mouse_click":
                button = Button.left if command.get("button") == "left" else Button.right
                self.mouse.click(button)
                
            elif action == "mouse_wheel":
                delta = command.get("delta", 0)
                self.mouse.scroll(0, delta)
                
            elif action == "key_press":
                key = command.get("key")
                if key in self.KEY_MAPPING:
                    self.keyboard.press(self.KEY_MAPPING[key])
                    self.keyboard.release(self.KEY_MAPPING[key])
                    
            elif action == "text_input":
                text = command.get("text", "")
                if text:
                    self.keyboard.type(text)
                    
        except Exception as e:
            self.log_message.emit(f"⚠️ Ошибка выполнения команды: {e}")
    
    def stop(self):
        """Остановка потока"""
        self.is_running = False
        self.is_connected = False


class RemoteAccessHostWindow(QMainWindow):
    """Главное окно хоста"""
    
    def __init__(self):
        super().__init__()
        self.host_thread = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Удалённый доступ - Хост")
        self.setGeometry(300, 300, 600, 500)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QVBoxLayout(central_widget)
        
        # Заголовок
        header = QLabel("ХОСТ УДАЛЕННОГО ДОСТУПА")
        header.setStyleSheet("""
            QLabel {
                background-color: #2c3e50;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        # Статус
        status_group = QGroupBox("Статус")
        status_group.setFont(QFont("Arial", 10, QFont.Bold))
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("ОСТАНОВЛЕН")
        self.status_label.setStyleSheet("color: red; font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        self.clients_label = QLabel("Клиентов: 0")
        status_layout.addWidget(self.clients_label)
        
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # Настройки
        settings_group = QGroupBox("Настройки")
        settings_group.setFont(QFont("Arial", 10, QFont.Bold))
        settings_layout = QGridLayout()
        
        settings_layout.addWidget(QLabel("Сервер:"), 0, 0)
        self.server_edit = QLineEdit("ws://130.49.149.152:9001")
        settings_layout.addWidget(self.server_edit, 0, 1)
        
        settings_layout.addWidget(QLabel("ID хоста:"), 1, 0)
        self.host_id_edit = QLineEdit("PC_HOME")
        settings_layout.addWidget(self.host_id_edit, 1, 1)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("ЗАПУСТИТЬ")
        self.start_btn.setStyleSheet("""
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
        self.start_btn.clicked.connect(self.start_host)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("ОСТАНОВИТЬ")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
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
        self.stop_btn.clicked.connect(self.stop_host)
        button_layout.addWidget(self.stop_btn)
        
        main_layout.addLayout(button_layout)
        
        # Журнал
        log_group = QGroupBox("Журнал")
        log_group.setFont(QFont("Arial", 10, QFont.Bold))
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
    
    def log(self, message):
        """Добавление сообщения в журнал"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # Прокрутка вниз
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
    
    def start_host(self):
        """Запуск хоста"""
        if not self.server_edit.text().startswith('ws://'):
            QMessageBox.warning(self, "Ошибка", "Сервер должен начинаться с ws://")
            return
        if not self.host_id_edit.text():
            QMessageBox.warning(self, "Ошибка", "Введите ID хоста")
            return
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("ПОДКЛЮЧЕНИЕ...")
        self.status_label.setStyleSheet("color: orange; font-size: 12px;")
        
        self.log("🚀 Запуск хоста...")
        
        self.host_thread = RemoteHostThread(
            relay_server=self.server_edit.text(),
            host_id=self.host_id_edit.text(),
            screenshot_interval=0.1
        )
        
        self.host_thread.log_message.connect(self.log)
        self.host_thread.status_changed.connect(self.on_status_changed)
        
        self.host_thread.start()
    
    def stop_host(self):
        """Остановка хоста"""
        if self.host_thread:
            self.host_thread.stop()
            self.host_thread = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("ОСТАНОВЛЕН")
        self.status_label.setStyleSheet("color: red; font-size: 12px;")
        self.clients_label.setText("Клиентов: 0")
        
        self.log("🛑 Хост остановлен")
    
    def on_status_changed(self, is_connected, clients_count):
        """Обработка изменения статуса"""
        if is_connected:
            self.status_label.setText("АКТИВЕН")
            self.status_label.setStyleSheet("color: green; font-size: 12px;")
            self.clients_label.setText(f"Клиентов: {clients_count}")
        else:
            self.status_label.setText("ОТКЛЮЧЕН")
            self.status_label.setStyleSheet("color: red; font-size: 12px;")
            self.clients_label.setText("Клиентов: 0")
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self.stop_host()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = RemoteAccessHostWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins')
    main()