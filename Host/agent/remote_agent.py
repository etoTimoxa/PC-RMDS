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
import socket
from datetime import datetime, timedelta
import pyautogui
import os
import re
import ctypes
from typing import Optional, Dict, Any, List
from ctypes import wintypes
import threading
import boto3
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QTextEdit, QGroupBox, 
                            QMessageBox, QSystemTrayIcon, QMenu, QStatusBar, 
                            QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QAction, QIcon, QPixmap, QColor

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController

from core.database_manager import DatabaseManager
from core.hardware_id import HardwareIDGenerator
from core.system_monitor import SystemActivityMonitor
from collectors.metrics_collector import SystemInfoCollector
from collectors.windows_events import WindowsEventCollector
from collectors.event_grouper import EventGrouper
from storage.json_logger import JSONLogger
from storage.cloud_uploader import CloudUploader
from utils.constants import METRICS_INTERVAL, WINDOWS_EVENTS_INTERVAL, ACTIVITY_UPDATE_INTERVAL
from agent.styles import APP_STYLE


class RemoteAgentThread(QThread):
    
    log_message = pyqtSignal(str)
    connection_status_changed = pyqtSignal(bool, int)
    client_connected = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    
    def __init__(self, relay_server: str, computer_data: Dict, 
                 screenshot_interval: float, quality: int = 70):
        super().__init__()
        self.relay_server = relay_server
        self.computer_data = computer_data
        self.computer_id = computer_data['computer_id']
        self.session_id = computer_data['session_id']
        self.session_token = computer_data.get('session_token', '')
        self.hostname = computer_data['hostname']
        self.screenshot_interval = screenshot_interval
        self.quality = quality
        self.is_running = True
        self.is_connected = False
        self.connected_clients = 0
        self.connected_clients_list = []
        self.streaming_clients = set()
        self.ws = None
        self.sending_screenshots = False
        
        self.json_logger = JSONLogger()
        self.json_logger.set_session(self.hostname, self.session_token)
        self.cloud_uploader = CloudUploader()
        self.event_grouper = EventGrouper()
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        try:
            self.screen_width, self.screen_height = pyautogui.size()
        except:
            self.screen_width, self.screen_height = 1920, 1080
    
    def update_settings(self, screenshot_interval: float = None, quality: int = None):
        if screenshot_interval is not None:
            self.screenshot_interval = screenshot_interval
        if quality is not None:
            self.quality = quality
    
    def run(self):
        asyncio.run(self.agent_main())
    
    async def collect_initial_metrics_and_events(self):
        metrics = SystemInfoCollector.get_performance_metrics()
        self.json_logger.add_metric(metrics)
        
        if self.json_logger.should_collect_events():
            events = WindowsEventCollector.get_events_last_30min()
            if events:
                grouped_events = self.event_grouper.group_events(events)
                self.json_logger.add_windows_events(grouped_events, is_initial=True)
    
    async def collect_metrics_periodically(self):
        while self.is_running:
            try:
                await asyncio.sleep(METRICS_INTERVAL)
                if not self.is_running:
                    break
                metrics = SystemInfoCollector.get_performance_metrics()
                self.json_logger.add_metric(metrics)
            except Exception as e:
                self.log_message.emit(f"Ошибка сбора метрик: {e}")
    
    async def collect_new_windows_events_periodically(self):
        while self.is_running:
            try:
                await asyncio.sleep(WINDOWS_EVENTS_INTERVAL)
                if not self.is_running:
                    break
                events = WindowsEventCollector.get_new_events()
                if events:
                    grouped_events = self.event_grouper.group_events(events)
                    self.json_logger.add_windows_events(grouped_events, is_initial=False)
            except Exception as e:
                self.log_message.emit(f"Ошибка сбора событий Windows: {e}")
    
    async def update_activity_periodically(self):
        while self.is_running and self.is_connected:
            try:
                await asyncio.sleep(ACTIVITY_UPDATE_INTERVAL)
                if self.session_id:
                    DatabaseManager.update_session_activity(self.session_id)
            except Exception as e:
                self.log_message.emit(f"Ошибка обновления активности: {e}")
    
    async def check_and_upload_at_midnight(self):
        while self.is_running:
            try:
                now = datetime.now()
                next_midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
                seconds_until_midnight = (next_midnight - now).total_seconds()
                await asyncio.sleep(seconds_until_midnight)
                
                if not self.is_running:
                    break
                
                self.json_logger.switch_to_new_day()
                uploaded = self.cloud_uploader.check_and_upload()
                if uploaded > 0:
                    DatabaseManager.update_json_sent_count(self.session_id, uploaded)
                
                events = WindowsEventCollector.get_events_last_30min()
                if events:
                    grouped_events = self.event_grouper.group_events(events)
                    self.json_logger.add_windows_events(grouped_events, is_initial=True)
                
                metrics = SystemInfoCollector.get_performance_metrics()
                self.json_logger.add_metric(metrics)
                
            except Exception as e:
                self.log_message.emit(f"Ошибка проверки полуночи: {e}")
    
    async def check_and_upload_on_startup(self):
        uploaded = self.cloud_uploader.check_and_upload()
        if uploaded > 0:
            DatabaseManager.update_json_sent_count(self.session_id, uploaded)
    
    async def check_urgent_upload(self):
        while self.is_running:
            try:
                await asyncio.sleep(60)
                self.cloud_uploader.check_and_upload()
            except:
                pass
    
    async def agent_main(self):
        reconnect_delay = 5
        
        await self.check_and_upload_on_startup()
        await self.collect_initial_metrics_and_events()
        
        tasks = [
            asyncio.create_task(self.collect_metrics_periodically()),
            asyncio.create_task(self.collect_new_windows_events_periodically()),
            asyncio.create_task(self.update_activity_periodically()),
            asyncio.create_task(self.check_and_upload_at_midnight()),
            asyncio.create_task(self.check_urgent_upload())
        ]
        
        while self.is_running:
            try:
                async with websockets.connect(self.relay_server) as ws:
                    self.ws = ws
                    self.is_connected = True
                    
                    register_msg = {
                        "type": "register_agent",
                        "data": {
                            "computer_id": self.computer_id,
                            "session_id": self.session_id,
                            "session_token": self.session_token,
                            "agent_id": self.hostname,
                            "hostname": self.hostname
                        }
                    }
                    await ws.send(json.dumps(register_msg))
                    self.log_message.emit(f"✅ Зарегистрирован на сервере")
                    
                    self.connection_status_changed.emit(True, self.connected_clients)
                    
                    await self.receive_commands(ws)
                    
            except Exception as e:
                self.log_message.emit(f"Ошибка подключения: {e}")
            
            self.is_connected = False
            self.connection_status_changed.emit(False, 0)
            
            if self.is_running:
                await asyncio.sleep(reconnect_delay)
        
        for task in tasks:
            task.cancel()
    
    async def send_system_info(self, ws):
        try:
            system_info = {
                "basic": SystemInfoCollector.get_basic_info(),
                "metrics": SystemInfoCollector.get_performance_metrics(),
                "timestamp": datetime.now().isoformat(),
                "computer_id": self.computer_id,
                "session_token": self.session_token
            }
            
            message = {
                "type": "system_info",
                "data": system_info,
                "computer_id": self.computer_id,
                "agent_id": self.hostname
            }
            
            await ws.send(json.dumps(message))
            return True
        except Exception as e:
            self.log_message.emit(f"Ошибка отправки system_info: {e}")
            return False
    
    async def screenshot_loop(self, ws):
        self.sending_screenshots = True
        
        while self.sending_screenshots and self.is_connected and len(self.streaming_clients) > 0:
            try:
                start_time = time.time()
                
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", quality=self.quality, optimize=True)
                    img_data = buffer.getvalue()
                    img_b64 = base64.b64encode(img_data).decode()
                    
                    message = {
                        "type": "screenshot",
                        "data": img_b64,
                        "computer_id": self.computer_id,
                        "agent_id": self.hostname
                    }
                    
                    await ws.send(json.dumps(message))
                
                elapsed = time.time() - start_time
                sleep_time = max(0, self.screenshot_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                self.log_message.emit(f"Ошибка в screenshot_loop: {e}")
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
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_connected.emit(client_id)
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
                
        except Exception as e:
            self.log_message.emit(f"Ошибка в receive_commands: {e}")
    
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
                await asyncio.sleep(0.01)
            
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
                else:
                    self.keyboard.type(text)
        except:
            pass
    
    def stop(self):
        self.log_message.emit("🛑 Остановка агента...")
        self.is_running = False
        self.is_connected = False
        self.streaming_clients.clear()
        self.connected_clients_list.clear()
        self.sending_screenshots = False
        
        DatabaseManager.update_computer_status(self.computer_id, False, self.session_id)
        self.log_message.emit(f"✅ Агент остановлен")


class RemoteAgentWindow(QMainWindow):
    
    def __init__(self, computer_data: Dict):
        super().__init__()
        self.computer_data = computer_data
        self.agent_thread = None
        self.tray_icon = None
        
        self.setWindowIcon(self.get_app_icon())
        
        DatabaseManager.set_current_session(computer_data['computer_id'], computer_data['session_id'])
        
        self.init_ui()
        self.load_settings()
        
        if self.auto_reconnect:
            QTimer.singleShot(1000, self.connect_to_server)
        
        if self.minimize_to_tray:
            self.hide()
            self.create_tray_icon()
    
    def get_app_icon(self) -> QIcon:
        icon_path = Path(__file__).parent.parent / "app_icon.ico"
        
        if not icon_path.exists():
            icon_path = Path(__file__).parent / "app_icon.ico"
        
        if not icon_path.exists():
            icon_path = Path.cwd() / "app_icon.ico"
        
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(255, 140, 66))
        return QIcon(pixmap)
    
    def init_ui(self):
        self.setWindowTitle("Remote Access Agent")
        self.setGeometry(300, 300, 550, 450)
        self.setStyleSheet(APP_STYLE)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #ff8c42; border-radius: 10px;")
        header_layout = QHBoxLayout(header_frame)
        
        title = QLabel("⚡ REMOTE ACCESS AGENT")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; padding: 12px;")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("settingsButton")  
        self.settings_btn.setFixedSize(36, 36)  
        self.settings_btn.setFont(QFont("Segoe UI", 14)) 
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.2);
                color: white;
                border-radius: 18px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.3); }
            QPushButton:pressed { background-color: rgba(255,255,255,0.4); }
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(self.settings_btn)
        header_layout.setContentsMargins(10, 5, 15, 5)
        main_layout.addWidget(header_frame)
        
        info_group = QGroupBox("ИНФОРМАЦИЯ О СИСТЕМЕ")
        info_layout = QVBoxLayout()
        
        self.computer_label = QLabel()
        self.computer_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff8c42;")
        self.computer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.computer_label.setText(f"🖥️ {self.computer_data['hostname']}")
        info_layout.addWidget(self.computer_label)
        
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 8px; padding: 10px;")
        status_layout = QVBoxLayout(status_frame)
        
        self.status_label = QLabel("● Не подключен")
        self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_label)
        
        info_layout.addWidget(status_frame)
        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)
        
        log_group = QGroupBox("ЖУРНАЛ СОБЫТИЙ")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        exit_frame = QFrame()
        exit_layout = QHBoxLayout(exit_frame)
        exit_layout.addStretch()
        
        self.exit_btn = QPushButton("✖ ВЫХОД")
        self.exit_btn.setFixedWidth(120)
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                padding: 8px;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        self.exit_btn.clicked.connect(self.quit_application)
        exit_layout.addWidget(self.exit_btn)
        main_layout.addWidget(exit_frame)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")
    
    def create_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        
        icon = self.windowIcon()
        
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Remote Access Agent")
        
        tray_menu = QMenu()
        
        show_action = QAction("👁 Показать окно", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        settings_action = QAction("⚙ Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("✖ Выход", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
    
    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()
    
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()
    
    def load_settings(self):
        settings = QSettings("RemoteAccess", "Agent")
        self.server = settings.value("server", "ws://localhost:9001")
        self.quality = int(settings.value("quality", 70))
        self.fps = float(settings.value("fps", 20))
        self.auto_reconnect = settings.value("auto_reconnect", True, type=bool)
        self.minimize_to_tray = settings.value("minimize_to_tray", True, type=bool)
    
    def open_settings(self):
        from agent.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec():
            dialog.save_settings()
            self.load_settings()
            
            if self.agent_thread and self.agent_thread.is_connected:
                interval = 1.0 / self.fps if self.fps > 0 else 0.05
                self.agent_thread.update_settings(interval, self.quality)
                self.log(f"Настройки обновлены")
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
    
    def connect_to_server(self):
        if not self.server.startswith('ws://'):
            QMessageBox.warning(self, "Ошибка", "Сервер должен начинаться с ws://")
            return
        
        self.log(f"Подключение к серверу: {self.server}")
        
        interval = 1.0 / self.fps if self.fps > 0 else 0.05
        
        self.agent_thread = RemoteAgentThread(
            relay_server=self.server,
            computer_data=self.computer_data,
            screenshot_interval=interval,
            quality=self.quality
        )
        
        self.agent_thread.log_message.connect(self.log)
        self.agent_thread.connection_status_changed.connect(self.on_connection_status_changed)
        self.agent_thread.client_connected.connect(self.on_client_connected)
        self.agent_thread.client_disconnected.connect(self.on_client_disconnected)
        
        self.agent_thread.start()
    
    def on_connection_status_changed(self, is_connected, clients_count):
        if is_connected:
            self.status_label.setText("● Подключен к серверу")
            self.status_label.setStyleSheet("font-size: 13px; color: #27ae60; font-weight: bold;")
            self.log("Подключен к серверу")
            self.status_bar.showMessage("Подключен к серверу")
            
            if self.tray_icon:
                self.tray_icon.setToolTip("Remote Access Agent - Подключен")
        else:
            self.status_label.setText("● Не подключен")
            self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
            self.status_bar.showMessage("Отключен от сервера")
            
            if self.tray_icon:
                self.tray_icon.setToolTip("Remote Access Agent - Отключен")
    
    def on_client_connected(self, client_id):
        if self.tray_icon:
            self.tray_icon.showMessage(
                "Новое подключение",
                f"Клиент {client_id} подключился",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def on_client_disconnected(self, client_id):
        pass
    
    def quit_application(self):
        reply = QMessageBox.question(
            self, "Подтверждение", "Вы уверены, что хотите выйти?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(3000)
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            QApplication.quit()
    
    def closeEvent(self, event):
        if self.minimize_to_tray and self.tray_icon:
            event.ignore()
            self.hide()
        else:
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(3000)
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            event.accept()