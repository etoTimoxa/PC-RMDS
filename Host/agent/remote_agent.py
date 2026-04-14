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
import threading
import boto3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from core.api_client import APIClient as DatabaseManager

# Импортируем Windows-специфичные модули только на Windows
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QTextEdit, QGroupBox, 
                            QMessageBox, QSystemTrayIcon, QMenu, QStatusBar, 
                            QFrame, QCheckBox, QDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QAction, QIcon, QPixmap, QColor, QScreen, QImage

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController

from core.api_client import APIClient
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
    
    def __init__(self, relay_server: str, computer_data: dict, 
                 screenshot_interval: float, quality: int = 60, max_resolution: tuple = (1280, 720)):
        super().__init__()
        self.relay_server = relay_server
        self.computer_data = computer_data
        self.computer_id = computer_data['computer_id']
        self.session_id = computer_data['session_id']
        self.session_token = computer_data.get('session_token', '')
        self.hostname = computer_data['hostname']
        self.screenshot_interval = screenshot_interval
        self.quality = quality
        self.max_resolution = max_resolution  # Максимальное разрешение для оптимизации
        self.is_running = True
        self.is_connected = False
        self.connected_clients = 0
        self.connected_clients_list = []
        self.streaming_clients = set()
        self.ws = None
        self.sending_screenshots = False
        self.adaptive_quality = quality  # Адаптивное качество
        self.network_speed_test_counter = 0  # Счетчик для проверки скорости сети
        self.fast_network = True  # Флаг быстрой сети
        
        self.json_logger = JSONLogger()
        self.cloud_uploader = CloudUploader(self.json_logger)
        self.json_logger.set_session(self.hostname, self.session_token, self.cloud_uploader)
        self.event_grouper = EventGrouper()
        self.initial_events_collected = False  # Флаг для предотвращения повторного сбора событий
        
        # Устанавливаем callback для логирования действий пользователя
        self._setup_user_action_callback()
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        try:
            self.screen_width, self.screen_height = pyautogui.size()
        except:
            self.screen_width, self.screen_height = 1920, 1080
    
    def _setup_user_action_callback(self):
        """Настраивает callback для логирования действий пользователя."""
        def on_user_action(action_type: str, description: str, details: dict):
            # Определяем тип пользователя (клиент или админ)
            # Приоритет: user_type из события (если есть) > role_id из computer_data
            user_type = details.get('user_type')
            if user_type:
                # Используем тип пользователя из события (client, admin, system)
                user_role = user_type
            else:
                # Fallback на role_id из computer_data
                user_role = 'client'
                if self.computer_data.get('role_id') in (2, 3):  # admin или superadmin
                    user_role = 'admin'
            
            # Определяем, удалённо ли выполнено действие
            is_remote = details.get('is_remote', False)
            
            # Добавляем действие в JSON лог
            self.json_logger.add_user_action(
                action_type=action_type,
                description=description,
                user_id=self.computer_data.get('computer_id'),
                user_login=self.computer_data.get('login'),
                user_role=user_role,
                is_remote=is_remote,
                details=details,
                force_write=True  # Сразу записываем важные события
            )
            
            self.log_message.emit(f"📝 Зафиксировано действие: {description}")
        
        # Устанавливаем callback в WindowsEventCollector
        WindowsEventCollector.set_user_action_callback(on_user_action)
    
    def _handle_system_shutdown(self):
        """Обрабатывает сигнал выключения/перезагрузки системы."""
        self.log_message.emit("⚠️ Обнаружена команда на выключение/перезагрузку системы")
        
        # Записываем событие в лог
        self.json_logger.add_user_action(
            action_type='shutdown',
            description='Выключение системы',
            user_id=self.computer_data.get('computer_id'),
            user_login=self.computer_data.get('login'),
            user_role='system',
            is_remote=False,
            details={'reason': 'system_shutdown', 'source': 'system_monitor'},
            force_write=True
        )
        
        # Останавливаем агент
        self.stop()
        
        # Завершаем приложение
        self._shutdown_app()
    
    def _shutdown_app(self):
        """Завершает приложение Qt."""
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()
        except Exception as e:
            print(f"Ошибка завершения приложения: {e}")
    
    def update_settings(self, screenshot_interval: float = None, quality: int = None, 
                       max_resolution: tuple = None):
        if screenshot_interval is not None:
            self.screenshot_interval = screenshot_interval
        if quality is not None:
            self.quality = quality
            self.adaptive_quality = quality
        if max_resolution is not None:
            self.max_resolution = max_resolution
    
    def run(self):
        asyncio.run(self.agent_main())
    
    async def collect_initial_metrics_and_events(self):
        # Пропускаем если события уже были собраны
        if self.initial_events_collected:
            return
            
        metrics = SystemInfoCollector.get_performance_metrics()
        self.json_logger.add_metric(metrics)
        
        if self.json_logger.should_collect_events():
            # Собираем события с момента последней загрузки системы
            # Это позволяет обнаружить перезагрузку/выключение, которые произошли до запуска агента
            events = WindowsEventCollector.get_events_since_boot()
            if events:
                # Сначала проверяем события перезагрузки/выключения/загрузки
                restart_shutdown_events = WindowsEventCollector.detect_restart_shutdown_events(events)
                if restart_shutdown_events:
                    for action_info in restart_shutdown_events:
                        action_type = action_info.get('action_type', 'shutdown')
                        # Вызываем callback для логирования действия
                        if WindowsEventCollector._user_action_callback:
                            from utils.constants import USER_ACTION_TYPES
                            description = USER_ACTION_TYPES.get(action_type, {}).get('description', action_type)
                            WindowsEventCollector._user_action_callback(action_type, description, action_info)
                        
                        # Если обнаружена перезагрузка или выключение или загрузка
                        if action_type in ('restart', 'shutdown', 'system_boot', 'windows_restart', 'windows_shutdown'):
                            self.log_message.emit(f"⚠️ Обнаружено: {description}")
                
                # Потом группируем и записываем все события
                grouped_events = self.event_grouper.group_events(events)
                self.json_logger.add_windows_events(grouped_events, is_initial=True)
                
                # Помечаем что начальная коллекция событий выполнена
                self.initial_events_collected = True
    
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
                    # Проверяем события перезагрузки/выключения
                    restart_shutdown_events = WindowsEventCollector.detect_restart_shutdown_events(events)
                    if restart_shutdown_events:
                        for action_info in restart_shutdown_events:
                            action_type = action_info.get('action_type', 'shutdown')
                            # Вызываем callback для логирования действия
                            if WindowsEventCollector._user_action_callback:
                                description = 'Перезагрузка компьютера' if action_type == 'restart' else 'Выключение компьютера'
                                WindowsEventCollector._user_action_callback(action_type, description, action_info)
                            
                            # Если обнаружена перезагрузка или выключение
                            if action_type in ('restart', 'shutdown'):
                                self.log_message.emit(f"⚠️ Обнаружено {description}")
                                # Запускаем обработку в отдельной задаче
                                asyncio.create_task(self._handle_system_shutdown_async())
                    
                    grouped_events = self.event_grouper.group_events(events)
                    self.json_logger.add_windows_events(grouped_events, is_initial=False)
            except Exception as e:
                self.log_message.emit(f"Ошибка сбора событий Windows: {e}")
    
    async def _handle_system_shutdown_async(self):
        """Асинхронная обработка сигнала выключения/перезагрузки системы."""
        try:
            # Даем время на запись в лог
            await asyncio.sleep(2)
            self._handle_system_shutdown()
        except Exception as e:
            print(f"Ошибка обработки выключения системы: {e}")
    
    async def update_activity_periodically(self):
        """Обновляет активность сессии на основе активности системы"""
        while self.is_running:
            try:
                await asyncio.sleep(ACTIVITY_UPDATE_INTERVAL)
                if self.session_id:
                    # Проверяем активность системы
                    if SystemActivityMonitor.is_system_active():
                        APIClient.update_session_activity(self.session_id)
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
                
                self.log_message.emit("Полночь, переключение на новый файл...")
                self.json_logger.switch_to_new_day()
                
                uploaded = self.cloud_uploader.check_and_upload()
                if uploaded > 0:
                    APIClient.update_json_sent_count(self.session_id, uploaded)
                    self.log_message.emit(f"Загружено файлов в облако: {uploaded}")
                
                events = WindowsEventCollector.get_events_last_30min()
                if events:
                    grouped_events = self.event_grouper.group_events(events)
                    self.json_logger.add_windows_events(grouped_events, is_initial=True)
                
                metrics = SystemInfoCollector.get_performance_metrics()
                self.json_logger.add_metric(metrics)
                
                # Проверяем и помечаем вчерашний файл для отправки
                if self.json_logger.check_and_mark_yesterday_file():
                    self.log_message.emit("Вчерашний файл помечен для отправки")
                
            except Exception as e:
                self.log_message.emit(f"Ошибка проверки полуночи: {e}")
    
    async def check_and_upload_on_startup(self):
        """Проверяет и загружает файлы при запуске"""
        uploaded = self.cloud_uploader.check_and_upload()
        if uploaded > 0:
            APIClient.update_json_sent_count(self.session_id, uploaded)
            self.log_message.emit(f"Загружено файлов при старте: {uploaded}")
        
        # Проверяем и помечаем вчерашний файл
        if self.json_logger.check_and_mark_yesterday_file():
            self.log_message.emit("Вчерашний файл помечен для отправки")
    
    async def check_urgent_upload(self):
        while self.is_running:
            try:
                await asyncio.sleep(60)
                uploaded = self.cloud_uploader.check_and_upload()
                if uploaded > 0:
                    DatabaseManager.update_json_sent_count(self.session_id, uploaded)
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
    
    def _optimize_screenshot(self, img):
        """Оптимизирует скриншот: уменьшает разрешение и подбирает качество"""
        # Уменьшаем разрешение если оно больше максимального
        max_width, max_height = self.max_resolution
        width, height = img.size
        
        if width > max_width or height > max_height:
            # Сохраняем пропорции
            ratio = min(max_width / width, max_height / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return img
    
    async def _adaptive_quality_control(self, send_time):
        """Адаптивная подстройка качества на основе времени отправки"""
        self.network_speed_test_counter += 1
        
        # Проверяем каждые 10 кадров
        if self.network_speed_test_counter >= 10:
            self.network_speed_test_counter = 0
            
            # Если отправка занимает больше 200мс - сеть медленная
            if send_time > 0.2:
                if self.fast_network:
                    self.fast_network = False
                    self.adaptive_quality = max(30, self.quality - 20)
                    self.log_message.emit(f"📉 Сеть медленная, качество: {self.adaptive_quality}%")
                else:
                    self.adaptive_quality = max(30, self.adaptive_quality - 5)
            else:
                # Если отправка быстрая - повышаем качество
                if not self.fast_network:
                    self.fast_network = True
                    self.adaptive_quality = min(self.quality, self.adaptive_quality + 10)
                    self.log_message.emit(f"📈 Сеть быстрая, качество: {self.adaptive_quality}%")
                else:
                    self.adaptive_quality = min(self.quality, self.adaptive_quality + 5)
    
    def _take_screenshot_qt(self):
        """Создает скриншот с помощью PyQt6 (без вспышки, работает на Linux)"""
        try:
            app = QApplication.instance()
            if app is None:
                return None
            
            screen = app.primaryScreen()
            if screen is None:
                return None
            
            # Захватываем весь экран
            pixmap = screen.grabWindow(0)  # 0 = весь экран
            
            if pixmap.isNull():
                return None
            
            # Конвертируем в PIL Image
            width = pixmap.width()
            height = pixmap.height()
            
            # Конвертируем QPixmap в QImage, затем в bytes
            image = pixmap.toImage()
            
            # Получаем сырые данные изображения
            ptr = image.constBits()
            ptr.setsize(image.byteCount())
            
            # Создаем PIL изображение из данных
            img = Image.frombytes("RGBA", (width, height), ptr.asstring())
            
            # Конвертируем в RGB (убираем альфа-канал)
            img = img.convert("RGB")
            
            return img
            
        except Exception as e:
            self.log_message.emit(f"Ошибка Qt скриншота: {e}")
            return None
    
    def _take_screenshot_linux_mss(self):
        """Создает скриншот на Linux через mss (для X11)."""
        try:
            with mss.mss() as sct:
                # Получаем список мониторов
                monitors = sct.monitors
                
                # Если есть мониторы, берем основной (индекс 1)
                # monitors[0] - это все мониторы вместе
                if len(monitors) > 1:
                    monitor = monitors[1]  # Основной монитор
                elif len(monitors) == 1:
                    monitor = monitors[0]
                else:
                    self.log_message.emit("Мониторы не найдены")
                    return None
                
                # Захватываем скриншот
                sct_img = sct.grab(monitor)
                
                # Конвертируем в PIL Image
                # mss возвращает данные в формате BGR для X11
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                
                return img
                
        except Exception as e:
            self.log_message.emit(f"Ошибка mss на Linux: {e}")
            return None
    
    def _take_screenshot(self):
        """Создает скриншот экрана (кроссплатформенно)"""
        if platform.system() == "Linux":
            # На Linux сначала пробуем mss (работает на X11)
            img = self._take_screenshot_linux_mss()
            if img is not None:
                return img
            
            # Если mss не сработал, пробуем PyQt6 как запасной вариант
            img = self._take_screenshot_qt()
            if img is not None:
                return img
            
            self.log_message.emit("Не удалось создать скриншот на Linux")
            return None
        else:
            # На Windows используем mss (быстрее)
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]  # Основной монитор
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    return img
            except Exception as e:
                self.log_message.emit(f"Ошибка mss: {e}")
                
                # На Windows тоже пробуем Qt как запасной вариант
                img = self._take_screenshot_qt()
                if img is not None:
                    return img
                
                self.log_message.emit("Не удалось создать скриншот")
                return None
    
    async def screenshot_loop(self, ws):
        self.sending_screenshots = True
        error_count = 0
        max_errors = 5  # Максимальное количество ошибок подряд перед остановкой
        
        while self.sending_screenshots and self.is_connected and self.is_running and len(self.streaming_clients) > 0:
            try:
                start_time = time.time()
                
                # Создаем скриншот
                img = self._take_screenshot()
                
                if img is None:
                    error_count += 1
                    if error_count >= max_errors:
                        self.log_message.emit(f"Слишком много ошибок скриншота ({max_errors}), остановка")
                        break
                    # Ждем немного перед следующей попыткой
                    await asyncio.sleep(1)
                    continue
                
                error_count = 0  # Сбрасываем счетчик ошибок при успешном скриншоте
                
                # Оптимизируем изображение
                img = self._optimize_screenshot(img)
                
                # Используем адаптивное качество
                current_quality = self.adaptive_quality
                
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=current_quality, optimize=True, progressive=True)
                img_data = buffer.getvalue()
                img_b64 = base64.b64encode(img_data).decode()
                
                message = {
                    "type": "screenshot",
                    "data": img_b64,
                    "computer_id": self.computer_id,
                    "agent_id": self.hostname,
                    "screen_width": self.screen_width,
                    "screen_height": self.screen_height
                }
                
                await ws.send(json.dumps(message))
                
                send_time = time.time() - start_time
                
                # Адаптивная подстройка качества
                await self._adaptive_quality_control(send_time)
                
                elapsed = time.time() - start_time
                sleep_time = max(0, self.screenshot_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                self.log_message.emit(f"Ошибка в screenshot_loop: {e}")
                error_count += 1
                if error_count >= max_errors:
                    break
                # Ждем перед следующей попыткой
                await asyncio.sleep(1)
        
        self.sending_screenshots = False
    
    async def receive_commands(self, ws):
        screenshot_task = None
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                # Извлекаем client_id из разных возможных полей
                client_id = data.get("client_id") or data.get("data", {}).get("client_id", "unknown")
                
                if cmd_type == "register_client":
                    # Сервер присылает register_client когда клиент подключается
                    if client_id not in self.connected_clients_list:
                        self.connected_clients += 1
                        self.connected_clients_list.append(client_id)
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_connected.emit(client_id)
                        self.log_message.emit(f"Клиент {client_id} подключен")
                
                elif cmd_type == "start_stream":
                    self.streaming_clients.add(client_id)
                    if not self.sending_screenshots and len(self.streaming_clients) > 0:
                        # Создаем задачу и сохраняем ссылку на нее
                        screenshot_task = asyncio.create_task(self.screenshot_loop(ws))
                        self.log_message.emit(f"Запуск трансляции для клиента {client_id}")
                
                elif cmd_type == "stop_stream":
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                        self.log_message.emit(f"Остановка трансляции")
                
                elif cmd_type == "unregister_client":
                    # Удаляем клиента из списков
                    if client_id in self.connected_clients_list:
                        self.connected_clients_list.remove(client_id)
                        self.connected_clients -= 1
                        self.connection_status_changed.emit(True, self.connected_clients)
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                
                elif cmd_type == "mouse_move":
                    # Извлекаем данные из поля data или command_data
                    command_data = data.get("data", {})
                    if not command_data:
                        command_data = data.get("command_data", {})
                    await self.handle_mouse_move(command_data)
                
                elif cmd_type == "mouse_click":
                    command_data = data.get("data", {})
                    if not command_data:
                        command_data = data.get("command_data", {})
                    await self.handle_mouse_click(command_data)
                
                elif cmd_type == "mouse_wheel":
                    command_data = data.get("data", {})
                    if not command_data:
                        command_data = data.get("command_data", {})
                    await self.handle_mouse_wheel(command_data)
                
                elif cmd_type == "keyboard_input":
                    command_data = data.get("data", {})
                    if not command_data:
                        command_data = data.get("command_data", {})
                    await self.handle_keyboard_input(command_data)
                
                elif cmd_type == "key_press":
                    # Альтернативный формат команды клавиатуры
                    command_data = data.get("data", {})
                    await self.handle_keyboard_input(command_data)
                
                elif cmd_type == "request_system_info":
                    # Отправляем системную информацию (можно реализовать отдельно)
                    self.log_message.emit("Запрос системной информации")
                
                else:
                    self.log_message.emit(f"Неизвестная команда: {cmd_type}")
                
        except Exception as e:
            self.log_message.emit(f"Ошибка в receive_commands: {e}")
        finally:
            # Отменяем задачу скриншотов при выходе
            if screenshot_task and not screenshot_task.done():
                screenshot_task.cancel()
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
        
        APIClient.update_computer_status(self.computer_id, False, self.session_id)
        self.log_message.emit(f"✅ Агент остановлен")


class RemoteAgentWindow(QMainWindow):
    
    def __init__(self, computer_data: dict):
        super().__init__()
        self.computer_data = computer_data
        self.agent_thread = None
        self.tray_icon = None
        
        self.setWindowIcon(self.get_app_icon())
        
        APIClient.set_current_session(computer_data['computer_id'], computer_data['session_id'])
        
        self.init_ui()
        self.load_settings()
        
        if self.auto_reconnect:
            QTimer.singleShot(1000, self.connect_to_server)
        
        if self.minimize_to_tray:
            self.hide()
            self.create_tray_icon()
    
    def get_app_icon(self) -> QIcon:
        """Возвращает иконку приложения (кроссплатформенно)"""
        # Определяем базовый путь для frozen/unfrozen состояния
        if getattr(sys, '_MEIPASS', None):
            # Запущено через PyInstaller
            base_path = Path(sys._MEIPASS)
        else:
            # Запущено в режиме разработки
            base_path = Path(__file__).parent.parent
        
        # Пробуем PNG (для Linux/AppImage)
        icon_path = base_path / "app_icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        # Пробуем ICO (для Windows)
        icon_path = base_path / "app_icon.ico"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        # Пробуем в текущей директории
        icon_path = Path.cwd() / "app_icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        icon_path = Path.cwd() / "app_icon.ico"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        # Если иконка не найдена, создаем цветной квадрат
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
        self.quality = int(settings.value("quality", 60))
        self.fps = float(settings.value("fps", 30))
        self.auto_reconnect = settings.value("auto_reconnect", True, type=bool)
        self.minimize_to_tray = settings.value("minimize_to_tray", True, type=bool)
        self.auto_auth = settings.value("auto_auth", True, type=bool)
        self.auto_start = settings.value("auto_start", True, type=bool)
        self.first_run = settings.value("first_run", True, type=bool)
        
        # При первом запуске устанавливаем значения по умолчанию
        if self.first_run:
            settings.setValue("first_run", False)
            settings.setValue("auto_start", True)
            settings.setValue("minimize_to_tray", True)
            settings.setValue("auto_reconnect", True)
            settings.setValue("auto_auth", True)
            self.auto_reconnect = True
            self.minimize_to_tray = True
            self.auto_auth = True
            self.auto_start = True
        
        # Всегда проверяем автозагрузку при запуске
        # Если автозагрузка включена, добавляем в реестр
        if self.auto_start:
            self.add_to_startup()
    
    def add_to_startup_on_first_run(self):
        """Добавляет приложение в автозагрузку (кроссплатформенно)"""
        if sys.platform == 'win32':
            self._add_to_startup_windows()
        else:
            self._add_to_startup_linux()
    
    def add_to_startup(self):
        """Добавляет приложение в автозагрузку (кроссплатформенно)"""
        if sys.platform == 'win32':
            self._add_to_startup_windows()
        else:
            self._add_to_startup_linux()
    
    def remove_from_startup(self):
        """Удаляет приложение из автозагрузки (кроссплатформенно)"""
        if sys.platform == 'win32':
            self._remove_from_startup_windows()
        else:
            self._remove_from_startup_linux()
    
    def _add_to_startup_windows(self):
        """Добавляет в автозагрузку Windows"""
        try:
            import winreg
            import os
            
            app_path = sys.executable if getattr(sys, 'frozen', False) else sys.executable
            app_dir = os.path.dirname(app_path) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            
            winreg.SetValueEx(key, "RemoteAccessAgent", 0, winreg.REG_SZ, 
                            f'"{app_path}"')
            
            winreg.CloseKey(key)
            
            startup_script = os.path.join(os.environ.get("APPDATA", ""), 
                                          r"Microsoft\Windows\Start Menu\Programs\Startup",
                                          "remote_access_agent_start.bat")
            
            os.makedirs(os.path.dirname(startup_script), exist_ok=True)
            
            with open(startup_script, 'w') as f:
                f.write(f'@echo off\n')
                f.write(f'cd /d "{app_dir}"\n')
                f.write(f'start "" "{app_path}"\n')
                
        except Exception as e:
            print(f"Ошибка добавления в автозагрузку Windows: {e}")
    
    def _add_to_startup_linux(self):
        """Добавляет в автозагрузку Linux через .desktop файл"""
        try:
            import os
            
            app_path = sys.executable if getattr(sys, 'frozen', False) else sys.executable
            app_dir = os.path.dirname(app_path) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            
            # Создаем .desktop файл для автозагрузки
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=Remote Access Agent
Comment=Remote Access Agent
Exec={app_path}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
            
            # Путь к автозагрузке пользователя
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            
            desktop_file = os.path.join(autostart_dir, "remote-access-agent.desktop")
            with open(desktop_file, 'w') as f:
                f.write(desktop_content)
            
            # Делаем файл исполняемым
            os.chmod(desktop_file, 0o755)
            
        except Exception as e:
            print(f"Ошибка добавления в автозагрузку Linux: {e}")
    
    def _remove_from_startup_windows(self):
        """Удаляет из автозагрузки Windows"""
        try:
            import winreg
            import os
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, "RemoteAccessAgent")
            except:
                pass
            winreg.CloseKey(key)
            
            startup_script = os.path.join(os.environ.get("APPDATA", ""), 
                                          r"Microsoft\Windows\Start Menu\Programs\Startup",
                                          "remote_access_agent_start.bat")
            if os.path.exists(startup_script):
                os.remove(startup_script)
        except Exception as e:
            print(f"Ошибка удаления из автозагрузки Windows: {e}")
    
    def _remove_from_startup_linux(self):
        """Удаляет из автозагрузки Linux"""
        try:
            import os
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, "remote-access-agent.desktop")
            if os.path.exists(desktop_file):
                os.remove(desktop_file)
        except Exception as e:
            print(f"Ошибка удаления из автозагрузки Linux: {e}")
    
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