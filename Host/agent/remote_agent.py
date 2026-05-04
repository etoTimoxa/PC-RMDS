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
import wave
import audioop
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from core.api_client import APIClient as DatabaseManager

# Импортируем Windows-специфичные модули только на Windows
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

from qtpy.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QTextEdit, QGroupBox, 
                            QMessageBox, QSystemTrayIcon, QMenu, QStatusBar, 
                            QFrame, QCheckBox, QDialog)
from qtpy.QtCore import Qt, QThread, QSettings, QTimer
from qtpy.QtCore import Signal as Signal
from qtpy.QtGui import QFont, QTextCursor, QAction, QIcon, QPixmap, QColor, QScreen, QImage

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
    
    log_message = Signal(str)
    connection_status_changed = Signal(bool, int)
    client_connected = Signal(str)
    client_disconnected = Signal(str)
    
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
        self.max_resolution = max_resolution
        self.is_running = True
        self.is_connected = False
        self.connected_clients = 0
        self.connected_clients_list = []
        self.streaming_clients = set()
        self.ws = None
        self.sending_screenshots = False
        self.adaptive_quality = quality
        self.network_speed_test_counter = 0
        self.fast_network = True
        
        # Поддержка множественных клиентов
        self.clients = {}  # client_id -> {"permissions": list, "streaming": bool}
        self.server_connected = False
        self.silent_mode_enabled = False
        self.server_control_enabled = False
        
        self.json_logger = JSONLogger()
        self.cloud_uploader = CloudUploader(self.json_logger)
        self.json_logger.set_session(self.hostname, self.session_token, self.cloud_uploader)
        self.event_grouper = EventGrouper()
        self.initial_events_collected = False
        
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
            user_type = details.get('user_type')
            if user_type:
                user_role = user_type
            else:
                user_role = 'client'
                if self.computer_data.get('role_id') in (2, 3):
                    user_role = 'admin'
            
            is_remote = details.get('is_remote', False)
            
            self.json_logger.add_user_action(
                action_type=action_type,
                description=description,
                user_id=self.computer_data.get('computer_id'),
                user_login=self.computer_data.get('login'),
                user_role=user_role,
                is_remote=is_remote,
                details=details,
                force_write=True
            )
            
            self.log_message.emit(f"📝 Зафиксировано действие: {description}")
        
        WindowsEventCollector.set_user_action_callback(on_user_action)
    
    def _handle_system_shutdown(self):
        """Обрабатывает сигнал выключения/перезагрузки системы."""
        self.log_message.emit("⚠️ Обнаружена команда на выключение/перезагрузку системы")
        
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
        
        self.stop()
        self._shutdown_app()
    
    def _shutdown_app(self):
        """Завершает приложение Qt."""
        try:
            from qtpy.QtWidgets import QApplication
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
        if self.initial_events_collected:
            return
            
        metrics = SystemInfoCollector.get_performance_metrics()
        self.json_logger.add_metric(metrics)
        
        if self.json_logger.should_collect_events():
            events = WindowsEventCollector.get_events_since_boot()
            if events:
                restart_shutdown_events = WindowsEventCollector.detect_restart_shutdown_events(events)
                if restart_shutdown_events:
                    for action_info in restart_shutdown_events:
                        action_type = action_info.get('action_type', 'shutdown')
                        if WindowsEventCollector._user_action_callback:
                            from utils.constants import USER_ACTION_TYPES
                            description = USER_ACTION_TYPES.get(action_type, {}).get('description', action_type)
                            WindowsEventCollector._user_action_callback(action_type, description, action_info)
                        
                        if action_type in ('restart', 'shutdown', 'system_boot', 'windows_restart', 'windows_shutdown'):
                            self.log_message.emit(f"⚠️ Обнаружено: {description}")
                
                grouped_events = self.event_grouper.group_events(events)
                self.json_logger.add_windows_events(grouped_events, is_initial=True)
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
                    restart_shutdown_events = WindowsEventCollector.detect_restart_shutdown_events(events)
                    if restart_shutdown_events:
                        for action_info in restart_shutdown_events:
                            action_type = action_info.get('action_type', 'shutdown')
                            if WindowsEventCollector._user_action_callback:
                                description = 'Перезагрузка компьютера' if action_type == 'restart' else 'Выключение компьютера'
                                WindowsEventCollector._user_action_callback(action_type, description, action_info)
                            
                            if action_type in ('restart', 'shutdown'):
                                self.log_message.emit(f"⚠️ Обнаружено {description}")
                                asyncio.create_task(self._handle_system_shutdown_async())
                    
                    grouped_events = self.event_grouper.group_events(events)
                    self.json_logger.add_windows_events(grouped_events, is_initial=False)
            except Exception as e:
                self.log_message.emit(f"Ошибка сбора событий Windows: {e}")
    
    async def _handle_system_shutdown_async(self):
        """Асинхронная обработка сигнала выключения/перезагрузки системы."""
        try:
            await asyncio.sleep(2)
            self._handle_system_shutdown()
        except Exception as e:
            print(f"Ошибка обработки выключения системы: {e}")
    
    async def update_activity_periodically(self):
        """Обновляет активность сессии каждые 5 минут"""
        while self.is_running:
            try:
                await asyncio.sleep(5 * 60)  # 5 минут
                if self.is_running and self.session_id:
                    success = APIClient.update_session_activity(self.session_id)
                    if success:
                        self.log_message.emit(f"🔄 Обновлена активность сессии {self.session_id}")
            except Exception as e:
                self.log_message.emit(f"Ошибка обновления активности: {e}")
    
    async def check_and_upload_at_midnight(self):
        """Проверяет наступление полуночи, переключает файлы и загружает в облако"""
        while self.is_running:
            try:
                now = datetime.now()
                # Вычисляем время до следующей полуночи
                next_midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
                seconds_until_midnight = (next_midnight - now).total_seconds()
                
                self.log_message.emit(f"⏰ Следующая проверка полуночи через {seconds_until_midnight/3600:.1f} часов")
                await asyncio.sleep(seconds_until_midnight)
                
                if not self.is_running:
                    break
                
                self.log_message.emit("=" * 50)
                self.log_message.emit("🕛 НАСТУПИЛА ПОЛНОЧЬ - ВЫПОЛНЯЮ ПЕРЕКЛЮЧЕНИЕ ДНЯ")
                self.log_message.emit("=" * 50)
                
                # 1. Переключаем JSON логгер на новый день (создает новый файл)
                self.json_logger.switch_to_new_day()
                self.log_message.emit(f"📄 Создан новый файл: {self.json_logger.current_file.name if self.json_logger.current_file else 'None'}")
                
                # 2. Загружаем все ожидающие файлы в облако
                uploaded = self.cloud_uploader.check_and_upload()
                if uploaded > 0:
                    try:
                        APIClient.update_json_sent_count(self.session_id, uploaded)
                        self.log_message.emit(f"☁️ Загружено файлов в облако: {uploaded}")
                    except Exception as e:
                        self.log_message.emit(f"⚠️ Ошибка обновления счетчика: {e}")
                
                # 3. Очищаем старые файлы (старше 2 дней)
                cleaned = self.cloud_uploader.verify_and_cleanup()
                if cleaned > 0:
                    self.log_message.emit(f"🧹 Очищено локальных файлов: {cleaned}")
                
                # 4. Собираем свежие события Windows за последние 30 минут
                try:
                    events = WindowsEventCollector.get_events_last_30min()
                    if events:
                        grouped_events = self.event_grouper.group_events(events)
                        self.json_logger.add_windows_events(grouped_events, is_initial=True)
                        self.log_message.emit(f"📋 Собрано событий после полуночи: {len(events)}")
                except Exception as e:
                    self.log_message.emit(f"⚠️ Ошибка сбора событий после полуночи: {e}")
                
                # 5. Собираем свежие метрики
                try:
                    metrics = SystemInfoCollector.get_performance_metrics()
                    self.json_logger.add_metric(metrics)
                    self.log_message.emit(f"📊 Собраны метрики после полуночи")
                except Exception as e:
                    self.log_message.emit(f"⚠️ Ошибка сбора метрик после полуночи: {e}")
                
                self.log_message.emit("=" * 50)
                self.log_message.emit("✅ ПЕРЕКЛЮЧЕНИЕ ДНЯ ЗАВЕРШЕНО")
                self.log_message.emit("=" * 50)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log_message.emit(f"❌ Ошибка в midnight handler: {e}")
                await asyncio.sleep(60)  # При ошибке ждем минуту и продолжаем
    
    async def check_and_upload_on_startup(self):
        """Проверяет и загружает файлы при запуске"""
        uploaded = self.cloud_uploader.check_and_upload()
        if uploaded > 0:
            APIClient.update_json_sent_count(self.session_id, uploaded)
            self.log_message.emit(f"Загружено файлов при старте: {uploaded}")
        
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
        
        # Инициализация аудио устройства тихо без логов
        try:
            import sounddevice as sd
            default_output_idx = sd.default.device[1]
        except:
            pass
        
        await self.check_and_upload_on_startup()
        await self.collect_initial_metrics_and_events()
        
        # Проверяем, не нужно ли создать файл для сегодняшнего дня
        # (на случай если агент запустился после полуночи)
        current_date = datetime.now().date()
        if self.json_logger.current_date != current_date:
            self.log_message.emit(f"📅 Обнаружено несоответствие дат: логгер={self.json_logger.current_date}, текущая={current_date}")
            self.json_logger.switch_to_new_day()
        
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
                    self.loop = asyncio.get_running_loop()
                    
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
        max_width, max_height = self.max_resolution
        width, height = img.size
        
        if width > max_width or height > max_height:
            ratio = min(max_width / width, max_height / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return img
    
    async def _adaptive_quality_control(self, send_time):
        """Адаптивная подстройка качества на основе времени отправки"""
        self.network_speed_test_counter += 1
        
        if self.network_speed_test_counter >= 10:
            self.network_speed_test_counter = 0
            
            if send_time > 0.2:
                if self.fast_network:
                    self.fast_network = False
                    self.adaptive_quality = max(30, self.quality - 20)
                    self.log_message.emit(f"📉 Сеть медленная, качество: {self.adaptive_quality}%")
                else:
                    self.adaptive_quality = max(30, self.adaptive_quality - 5)
            else:
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
            
            pixmap = screen.grabWindow(0)
            
            if pixmap.isNull():
                return None
            
            width = pixmap.width()
            height = pixmap.height()
            
            image = pixmap.toImage()
            
            ptr = image.constBits()
            ptr.setsize(image.byteCount())
            
            img = Image.frombytes("RGBA", (width, height), ptr.asstring())
            img = img.convert("RGB")
            
            return img
            
        except Exception as e:
            self.log_message.emit(f"Ошибка Qt скриншота: {e}")
            return None
    
    def _take_screenshot_linux_mss(self):
        """Создает скриншот на Linux через mss (для X11)."""
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                
                if len(monitors) > 1:
                    monitor = monitors[1]
                elif len(monitors) == 1:
                    monitor = monitors[0]
                else:
                    self.log_message.emit("Мониторы не найдены")
                    return None
                
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                
                return img
                
        except Exception as e:
            self.log_message.emit(f"Ошибка mss на Linux: {e}")
            return None
    
    def _take_screenshot(self):
        """Создает скриншот экрана (кроссплатформенно)"""
        if platform.system() == "Linux":
            img = self._take_screenshot_linux_mss()
            if img is not None:
                return img
            
            img = self._take_screenshot_qt()
            if img is not None:
                return img
            
            self.log_message.emit("Не удалось создать скриншот на Linux")
            return None
        else:
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    return img
            except Exception as e:
                self.log_message.emit(f"Ошибка mss: {e}")
                
                img = self._take_screenshot_qt()
                if img is not None:
                    return img
                
                self.log_message.emit("Не удалось создать скриншот")
                return None
    
    async def audio_capture_loop(self, ws):
        self.sending_audio = True
        try:
            import sounddevice as sd
            
            self.log_message.emit("=" * 50)
            self.log_message.emit("📢 ДОСТУПНЫЕ АУДИО УСТРОЙСТВА:")
            self.log_message.emit("=" * 50)
            
            devices = sd.query_devices()
            default_output_idx = sd.default.device[1]
            
            for idx, dev in enumerate(devices):
                dev_type = "ВЫВОД" if dev['max_output_channels'] > 0 else "ВВОД "
                default_mark = "✅ ПО УМОЛЧАНИЮ" if idx == default_output_idx else ""
                self.log_message.emit(f"#{idx} | {dev_type} | {dev['name'][:45]} | каналов={dev['max_output_channels']} | sr={dev['default_samplerate']} {default_mark}")
            
            self.log_message.emit("=" * 50)
            
            # ✅ ЗАХВАТ УСТРОЙСТВА ВОСПРОИЗВЕДЕНИЯ ПО УМОЛЧАНИЮ
            target_device = default_output_idx
            
            self.log_message.emit(f"🎧 ИСПОЛЬЗУЕМ УСТРОЙСТВО #{target_device}: {devices[target_device]['name']}")
            self.log_message.emit("✅ Запуск захвата звука")
            
            sample_rate = 48000
            channels = 2
            blocksize = 2048
            
            def audio_callback(indata, frames, time, status):
                if self.sending_audio and self.is_connected:
                    try:
                        # Нормализуем громкость
                        audio_data = audioop.mul(indata.tobytes(), 2, 3.0)
                        audio_b64 = base64.b64encode(audio_data).decode()
                        asyncio.run_coroutine_threadsafe(
                            ws.send(json.dumps({
                                "type": "audio_chunk",
                                "data": audio_b64,
                                "computer_id": self.computer_id,
                                "agent_id": self.hostname,
                                "sample_rate": sample_rate,
                                "channels": channels,
                                "format": "int16"
                            })),
                            self.loop
                        )
                    except:
                        pass

            # Открываем поток на устройстве вывода
            with sd.InputStream(
                device=target_device,
                samplerate=sample_rate,
                channels=channels,
                blocksize=blocksize,
                callback=audio_callback,
                dtype='int16'
            ):
                self.log_message.emit(f"✅ Захват системного звука запущен: {sd.query_devices(target_device)['name']}")
                
                while self.sending_audio and len(self.streaming_clients) > 0:
                    await asyncio.sleep(0.1)

        except Exception as e:
            self.log_message.emit(f"Ошибка аудио захвата: {e}")
        finally:
            self.sending_audio = False

    async def screenshot_loop(self, ws):
        self.sending_screenshots = True
        error_count = 0
        max_errors = 5
        
        while self.sending_screenshots and self.is_connected and self.is_running and len(self.streaming_clients) > 0:
            try:
                start_time = time.time()
                
                img = self._take_screenshot()
                
                if img is None:
                    error_count += 1
                    if error_count >= max_errors:
                        self.log_message.emit(f"Слишком много ошибок скриншота ({max_errors}), остановка")
                        break
                    await asyncio.sleep(1)
                    continue
                
                error_count = 0
                
                img = self._optimize_screenshot(img)
                
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
                await asyncio.sleep(1)
        
        self.sending_screenshots = False
    
    async def receive_commands(self, ws):
        screenshot_task = None
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                client_id = data.get("client_id") or data.get("data", {}).get("client_id", "unknown")
                
                if cmd_type == "register_client":
                    if client_id not in self.connected_clients_list:
                        self.connected_clients += 1
                        self.connected_clients_list.append(client_id)
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_connected.emit(client_id)
                        self.log_message.emit(f"Клиент {client_id} подключен")
                
                elif cmd_type == "start_stream":
                    self.streaming_clients.add(client_id)
                    if not self.sending_screenshots and len(self.streaming_clients) > 0:
                        screenshot_task = asyncio.create_task(self.screenshot_loop(ws))
                        self.log_message.emit(f"Запуск трансляции для клиента {client_id}")
                
                elif cmd_type == "stop_stream":
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                        self.log_message.emit(f"Остановка трансляции")
                        # Сбрасываем регистрацию компьютера на сервере (ставим статус не в трансляции)
                        try:
                            APIClient.update_computer_status(self.computer_id, False, self.session_id)
                            self.log_message.emit(f"✅ Регистрация на сервере сброшена, компьютер помечен как не в трансляции")
                        except Exception as e:
                            self.log_message.emit(f"⚠️ Ошибка сброса регистрации на сервере: {e}")
                
                elif cmd_type == "unregister_client":
                    if client_id in self.connected_clients_list:
                        self.connected_clients_list.remove(client_id)
                        self.connected_clients -= 1
                        self.connection_status_changed.emit(True, self.connected_clients)
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                        # Сбрасываем регистрацию компьютера на сервере при отключении последнего клиента
                        try:
                            APIClient.update_computer_status(self.computer_id, False, self.session_id)
                            self.log_message.emit(f"✅ Регистрация на сервере сброшена, компьютер помечен как не в трансляции")
                        except Exception as e:
                            self.log_message.emit(f"⚠️ Ошибка сброса регистрации на сервере: {e}")
                
                elif cmd_type == "mouse_move":
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
                    command_data = data.get("data", {})
                    await self.handle_keyboard_input(command_data)
                
                elif cmd_type == "request_system_info":
                    self.log_message.emit("Запрос системной информации")
                
                else:
                    self.log_message.emit(f"Неизвестная команда: {cmd_type}")
                
        except Exception as e:
            self.log_message.emit(f"Ошибка в receive_commands: {e}")
        finally:
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
    
    def close_session(self):
        """Закрывает текущую сессию (статус = 2)"""
        if self.session_id:
            self.log_message.emit(f"🔒 Закрытие сессии {self.session_id}...")
            try:
                success = APIClient.close_session_by_id(self.session_id)
                if success:
                    self.log_message.emit(f"✅ Сессия {self.session_id} закрыта")
                else:
                    self.log_message.emit(f"⚠️ Не удалось закрыть сессию {self.session_id}")
            except Exception as e:
                self.log_message.emit(f"⚠️ Ошибка закрытия сессии: {e}")
    
    def stop(self):
        self.log_message.emit("🛑 Остановка агента...")
        self.is_running = False
        self.is_connected = False
        self.streaming_clients.clear()
        self.connected_clients_list.clear()
        self.sending_screenshots = False
        
        # Закрываем сессию при остановке
        self.close_session()
        
        # Обновляем статус компьютера на офлайн
        try:
            APIClient.update_computer_status(self.computer_id, False, self.session_id)
        except Exception as e:
            self.log_message.emit(f"⚠️ Ошибка обновления статуса: {e}")
        
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
        if getattr(sys, '_MEIPASS', None):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent.parent
        
        icon_path = base_path / "app_icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        icon_path = base_path / "app_icon.ico"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        icon_path = Path.cwd() / "app_icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
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
        self.quality = int(settings.value("quality", 60))
        self.fps = float(settings.value("fps", 30))
        self.auto_reconnect = settings.value("auto_reconnect", True, type=bool)
        self.minimize_to_tray = settings.value("minimize_to_tray", True, type=bool)
        self.auto_auth = settings.value("auto_auth", True, type=bool)
        self.auto_start = settings.value("auto_start", True, type=bool)
        self.first_run = settings.value("first_run", True, type=bool)
        
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
            
            app_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
            
            # Используем только реестр - самый надежный метод без лишних файлов
            key = None
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                    r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                    0, winreg.KEY_ALL_ACCESS)
                
                winreg.SetValueEx(key, "RemoteAccessAgent", 0, winreg.REG_SZ, 
                                f'"{app_path}"')
                
                self.log("✅ Добавлено в автозагрузку Windows (реестр)")
            except Exception as reg_err:
                self.log(f"⚠️ Не удалось добавить в реестр: {reg_err}")
            finally:
                if key:
                    winreg.CloseKey(key)
            
            # Удаляем старый батник чтобы не было двойного запуска
            try:
                startup_script = os.path.join(os.environ.get("APPDATA", ""), 
                                            r"Microsoft\Windows\Start Menu\Programs\Startup",
                                            "remote_access_agent_start.bat")
                if os.path.exists(startup_script):
                    os.remove(startup_script)
                    self.log("🗑️ Удален старый файл автозагрузки")
            except:
                pass
                
        except Exception as e:
            self.log(f"❌ Ошибка добавления в автозагрузку Windows: {e}")
    
    def _add_to_startup_linux(self):
        """Добавляет в автозагрузку Linux через .desktop файл"""
        try:
            import os
            
            app_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
            
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=Remote Access Agent
Comment=Remote Access Agent
Exec={app_path}
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
StartupNotify=false
"""
            
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True, mode=0o700)
            
            desktop_file = os.path.join(autostart_dir, "remote-access-agent.desktop")
            with open(desktop_file, 'w') as f:
                f.write(desktop_content)
            
            os.chmod(desktop_file, 0o644)
            self.log("✅ Добавлено в автозагрузку Linux (.desktop файл)")
            
        except Exception as e:
            self.log(f"❌ Ошибка добавления в автозагрузку Linux: {e}")
    
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
            # Закрываем сессию перед выходом
            session_id = self.computer_data.get('session_id')
            if session_id:
                print(f"[MAIN] Завершение работы, закрываем сессию {session_id}...")
                try:
                    DatabaseManager.close_session_by_id(session_id)
                    print(f"[MAIN] ✅ Сессия {session_id} закрыта")
                except Exception as e:
                    print(f"[MAIN] ❌ Ошибка закрытия сессии: {e}")
            
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
            # Закрываем сессию при закрытии окна
            session_id = self.computer_data.get('session_id')
            if session_id:
                print(f"[MAIN] Закрытие окна, закрываем сессию {session_id}...")
                try:
                    DatabaseManager.close_session_by_id(session_id)
                except Exception as e:
                    print(f"[MAIN] Ошибка закрытия сессии: {e}")
            
            if self.agent_thread:
                self.agent_thread.stop()
                self.agent_thread.wait(3000)
            
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            event.accept()