import sys
import asyncio
import websockets
import json
import mss
from io import BytesIO
from PIL import Image
import base64
import time
import platform
import psutil
import socket
from datetime import datetime
import pyautogui

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTextEdit, QGroupBox, QGridLayout, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController


class SystemInfoCollector:
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
            
            return {
                "cpu_model": cpu_model,
                "cpu_cores": cpu_cores,
                "cpu_physical_cores": cpu_physical_cores,
                "ram_total": round(ram_total, 2),
                "storage_total": round(storage_total, 2),
                "gpu_model": "Unknown"
            }
        except:
            return {}
    
    @staticmethod
    def get_performance_metrics():
        try:
            cpu_usage = psutil.cpu_percent(interval=0.5)
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
        self.connected_clients_list = []
        self.streaming_clients = set()
        self.ws = None
        self.sending_screenshots = False
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        try:
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
                    
                    register_msg = {
                        "type": "register_host",
                        "data": {"host_id": self.host_id},
                        "host_id": self.host_id
                    }
                    await ws.send(json.dumps(register_msg))
                    
                    self.is_connected = True
                    self.status_changed.emit(True, self.connected_clients)
                    
                    await self.receive_commands(ws)
                    
            except Exception as e:
                self.log_message.emit(f"Ошибка: {e}")
            
            self.is_connected = False
            self.connected_clients = 0
            self.connected_clients_list.clear()
            self.streaming_clients.clear()
            self.sending_screenshots = False
            self.status_changed.emit(False, 0)
            
            if self.is_running:
                await asyncio.sleep(reconnect_delay)
    
    async def send_system_info(self, ws):
        try:
            system_info = {
                "basic": SystemInfoCollector.get_basic_info(),
                "hardware": SystemInfoCollector.get_hardware_config(),
                "metrics": SystemInfoCollector.get_performance_metrics(),
                "timestamp": datetime.now().isoformat()
            }
            
            message = {
                "type": "system_info",
                "data": system_info,
                "host_id": self.host_id
            }
            
            await ws.send(json.dumps(message))
            return True
        except:
            return False
    
    async def screenshot_loop(self, ws):
        self.sending_screenshots = True
        frame_count = 0
        
        while self.sending_screenshots and self.is_connected and len(self.streaming_clients) > 0:
            try:
                start_time = time.time()
                
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", quality=70, optimize=True)
                    img_data = buffer.getvalue()
                    img_b64 = base64.b64encode(img_data).decode()
                    
                    message = {
                        "type": "screenshot",
                        "data": img_b64,
                        "host_id": self.host_id
                    }
                    
                    await ws.send(json.dumps(message))
                    frame_count += 1
                
                elapsed = time.time() - start_time
                sleep_time = max(0, self.screenshot_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except:
                break
        
        self.sending_screenshots = False
    
    async def receive_commands(self, ws):
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                client_id = data.get("client_id", "unknown")
                
                if cmd_type == "register_client":
                    if client_id not in self.connected_clients_list:
                        self.connected_clients += 1
                        self.connected_clients_list.append(client_id)
                        self.status_changed.emit(True, self.connected_clients)
                        await self.send_system_info(ws)
                
                elif cmd_type == "start_stream":
                    self.streaming_clients.add(client_id)
                    
                    if not self.sending_screenshots and len(self.streaming_clients) > 0:
                        asyncio.create_task(self.screenshot_loop(ws))
                
                elif cmd_type == "stop_stream":
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                
                elif cmd_type == "request_system_info":
                    await self.send_system_info(ws)
                
                elif cmd_type == "mouse_move":
                    await self.handle_mouse_move(data.get("data", {}))
                
                elif cmd_type == "mouse_click":
                    await self.handle_mouse_click(data.get("data", {}))
                
                elif cmd_type == "mouse_wheel":
                    await self.handle_mouse_wheel(data.get("data", {}))
                
                elif cmd_type == "keyboard_input":
                    await self.handle_keyboard_input(data.get("data", {}))
                
                elif cmd_type == "command":
                    await self.handle_command(data.get("data", {}))
                    
        except:
            self.streaming_clients.clear()
            self.sending_screenshots = False
    
    async def handle_mouse_move(self, command_data):
        try:
            x = command_data.get("x")
            y = command_data.get("y")
            if x is not None and y is not None:
                self.mouse.position = (x, y)
        except:
            pass
    
    async def handle_mouse_click(self, command_data):
        try:
            button_name = command_data.get("button", "left")
            x = command_data.get("x")
            y = command_data.get("y")
            
            if x is not None and y is not None:
                self.mouse.position = (x, y)
                time.sleep(0.01)
            
            button = Button.left if button_name == "left" else Button.right
            self.mouse.click(button)
        except:
            pass
    
    async def handle_mouse_wheel(self, command_data):
        try:
            delta = command_data.get("delta", 0)
            self.mouse.scroll(0, delta)
        except:
            pass
    
    async def handle_keyboard_input(self, command_data):
        try:
            text = command_data.get("text", "")
            if text:
                if text == '\b':
                    self.keyboard.press(Key.backspace)
                    self.keyboard.release(Key.backspace)
                elif text == '\r' or text == '\n':
                    self.keyboard.press(Key.enter)
                    self.keyboard.release(Key.enter)
                elif text == '\t':
                    self.keyboard.press(Key.tab)
                    self.keyboard.release(Key.tab)
                elif text == '\x1b':
                    self.keyboard.press(Key.esc)
                    self.keyboard.release(Key.esc)
                elif text == '\x7f':
                    self.keyboard.press(Key.delete)
                    self.keyboard.release(Key.delete)
                elif text == '\x1b[D':
                    self.keyboard.press(Key.left)
                    self.keyboard.release(Key.left)
                elif text == '\x1b[C':
                    self.keyboard.press(Key.right)
                    self.keyboard.release(Key.right)
                elif text == '\x1b[A':
                    self.keyboard.press(Key.up)
                    self.keyboard.release(Key.up)
                elif text == '\x1b[B':
                    self.keyboard.press(Key.down)
                    self.keyboard.release(Key.down)
                elif text == '\x1b[H':
                    self.keyboard.press(Key.home)
                    self.keyboard.release(Key.home)
                elif text == '\x1b[F':
                    self.keyboard.press(Key.end)
                    self.keyboard.release(Key.end)
                elif text == '\x1b[5~':
                    self.keyboard.press(Key.page_up)
                    self.keyboard.release(Key.page_up)
                elif text == '\x1b[6~':
                    self.keyboard.press(Key.page_down)
                    self.keyboard.release(Key.page_down)
                else:
                    self.keyboard.type(text)
        except:
            pass
    
    async def handle_command(self, command_data):
        try:
            action = command_data.get("action")
            
            if action == "text_input":
                text = command_data.get("text", "")
                if text:
                    self.keyboard.type(text)
            
            elif action == "key_press":
                key = command_data.get("key")
                if key in self.KEY_MAPPING:
                    self.keyboard.press(self.KEY_MAPPING[key])
                    self.keyboard.release(self.KEY_MAPPING[key])
                    
        except:
            pass
    
    def stop(self):
        self.is_running = False
        self.is_connected = False
        self.streaming_clients.clear()
        self.connected_clients_list.clear()
        self.sending_screenshots = False


class RemoteAccessHostWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.host_thread = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Удалённый доступ - Хост")
        self.setGeometry(300, 300, 600, 500)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
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
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)
        
        status_group = QGroupBox("Статус")
        font = QFont("Arial", 10, QFont.Weight.Bold)
        status_group.setFont(font)
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("ОСТАНОВЛЕН")
        self.status_label.setStyleSheet("color: red; font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        self.clients_label = QLabel("Клиентов: 0")
        status_layout.addWidget(self.clients_label)
        
        self.streaming_label = QLabel("Трансляция: Нет")
        self.streaming_label.setStyleSheet("color: gray; font-size: 11px;")
        status_layout.addWidget(self.streaming_label)
        
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        settings_group = QGroupBox("Настройки")
        settings_group.setFont(font)
        settings_layout = QGridLayout()
        
        settings_layout.addWidget(QLabel("Сервер:"), 0, 0)
        self.server_edit = QLineEdit("ws://130.49.149.152:9001")
        settings_layout.addWidget(self.server_edit, 0, 1)
        
        settings_layout.addWidget(QLabel("ID хоста:"), 1, 0)
        self.host_id_edit = QLineEdit("PC_HOME")
        settings_layout.addWidget(self.host_id_edit, 1, 1)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
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
        
        log_group = QGroupBox("Журнал")
        log_group.setFont(font)
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
    
    def start_host(self):
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
        
        self.log("Запуск хоста...")
        
        interval = 0.05
        
        self.host_thread = RemoteHostThread(
            relay_server=self.server_edit.text(),
            host_id=self.host_id_edit.text(),
            screenshot_interval=interval
        )
        
        self.host_thread.log_message.connect(self.log)
        self.host_thread.status_changed.connect(self.on_status_changed)
        
        self.host_thread.start()
    
    def stop_host(self):
        if self.host_thread:
            self.host_thread.stop()
            self.host_thread = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("ОСТАНОВЛЕН")
        self.status_label.setStyleSheet("color: red; font-size: 12px;")
        self.clients_label.setText("Клиентов: 0")
        self.streaming_label.setText("Трансляция: Нет")
        self.streaming_label.setStyleSheet("color: gray; font-size: 11px;")
        
        self.log("Хост остановлен")
    
    def on_status_changed(self, is_connected, clients_count):
        if is_connected:
            self.status_label.setText("АКТИВЕН")
            self.status_label.setStyleSheet("color: green; font-size: 12px;")
            self.clients_label.setText(f"Клиентов: {clients_count}")
            
            if self.host_thread and len(self.host_thread.streaming_clients) > 0:
                self.streaming_label.setText(f"Трансляция: Да ({len(self.host_thread.streaming_clients)} клиентов)")
                self.streaming_label.setStyleSheet("color: green; font-size: 11px;")
            else:
                self.streaming_label.setText("Трансляция: Нет")
                self.streaming_label.setStyleSheet("color: gray; font-size: 11px;")
        else:
            self.status_label.setText("ОТКЛЮЧЕН")
            self.status_label.setStyleSheet("color: red; font-size: 12px;")
            self.clients_label.setText("Клиентов: 0")
            self.streaming_label.setText("Трансляция: Нет")
            self.streaming_label.setStyleSheet("color: gray; font-size: 11px;")
    
    def closeEvent(self, event):
        self.stop_host()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = RemoteAccessHostWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()