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
from typing import Dict, List, Optional, Tuple, Any, Callable

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

# ─── Diagnostics subsystem ──────────────────────────────────────────────
from agent.diagnostics import (
    AgentFSM,
    AgentState,
    DiagnosticEvent,
    Severity,
    DiagnosticEventStore,
    RecoveryManager,
    RecoveryResult,
    RecoveryAction,
    StructuredLogger,
    HeartbeatSender,
    ACKSender,
    ScreenshotWatchdog,
)

HEARTBEAT_INTERVAL = 5
WATCHDOG_CHECK_INTERVAL = 2.0
SCREENSHOT_STALL_TIMEOUT = 5.0
DIAGNOSTIC_SEND_INTERVAL = 30.0
RECONNECT_BASE_DELAY = 5.0
MAX_CONSECUTIVE_ERRORS = 10


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
        self.sending_audio = False
        self.adaptive_quality = quality
        self.network_speed_test_counter = 0
        self.fast_network = True
        
        # Поддержка множественных клиентов
        self.clients = {}
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
        except Exception:
            self.screen_width, self.screen_height = 1920, 1080

        # ─── Diagnostics subsystem initialization ───────────────────
        self._init_diagnostics()

    def _init_diagnostics(self) -> None:
        """Initialize all diagnostics subsystem components."""
        agent_id = self.hostname

        # 1. FSM
        self.fsm = AgentFSM(
            initial_state=AgentState.DISCONNECTED,
            on_transition=self._on_fsm_transition,
        )

        # 2. Diagnostic events store
        self.event_store = DiagnosticEventStore(max_events=1000)

        # 3. Structured logger per component
        self.diag_logger = StructuredLogger("agent", agent_id=agent_id)

        # 4. Heartbeat sender
        self.heartbeat = HeartbeatSender(agent_id=agent_id, interval=HEARTBEAT_INTERVAL)

        # 5. ACK sender
        self.ack_sender = ACKSender()
        self.ack_sender.set_agent_id(agent_id)

        # 6. Screenshot watchdog
        self.watchdog = ScreenshotWatchdog(
            agent_id=agent_id,
            stall_timeout=SCREENSHOT_STALL_TIMEOUT,
            check_interval=WATCHDOG_CHECK_INTERVAL,
        )
        self.watchdog.set_on_stall(self._on_screenshot_stall)

        # 7. Recovery manager
        self.recovery_mgr = RecoveryManager(
            global_cooldown=10.0,
            max_attempts=5,
        )
        self._register_recovery_handlers()

        # 8. Diagnostics tasks container
        self.diagnostics_tasks: List[asyncio.Task] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # 9. Consecutive error counter for backoff
        self._consecutive_errors: int = 0

    def _on_fsm_transition(self, old: AgentState, new: AgentState) -> None:
        """Callback for FSM state transitions."""
        self.diag_logger.info(
            "state_transition",
            f"Agent state: {old.value} -> {new.value}",
            {"from": old.value, "to": new.value},
        )

    def _register_recovery_handlers(self) -> None:
        """Register all recovery action handlers with validators."""
        self.recovery_mgr.register_handler(
            RecoveryAction.RECONNECT_WEBSOCKET,
            self._reconnect_websocket_handler,
            self._validate_websocket,
        )
        self.recovery_mgr.register_handler(
            RecoveryAction.RESTART_STREAM,
            self._restart_stream_handler,
            self._validate_stream,
        )
        self.recovery_mgr.register_handler(
            RecoveryAction.RESTORE_SESSION,
            self._restore_session_handler,
            self._validate_session,
        )
        self.recovery_mgr.register_handler(
            RecoveryAction.RESTART_TASKS,
            self._restart_tasks_handler,
            self._validate_tasks,
        )

    # ─── Recovery handlers ──────────────────────────────────────────

    async def _reconnect_websocket_handler(self) -> bool:
        """Reconnect WebSocket and restore session."""
        self.diag_logger.info("reconnect_started", "Starting WebSocket reconnection")
        close_code = 1000
        if self.ws and hasattr(self.ws, 'open') and self.ws.open:
            try:
                await self.ws.close(code=close_code, reason="reconnecting")
            except Exception:
                pass
        self.ws = None
        self.is_connected = False
        await asyncio.sleep(RECONNECT_BASE_DELAY)
        return True

    async def _validate_websocket(self) -> bool:
        """Validate that WebSocket is properly connected."""
        return self.ws is not None and hasattr(self.ws, 'open') and self.ws.open

    async def _restart_stream_handler(self) -> bool:
        """Restart screenshot stream."""
        self.diag_logger.info("restart_stream", "Restarting screenshot stream")
        self.sending_screenshots = False
        await asyncio.sleep(1.0)
        if len(self.streaming_clients) > 0:
            self.sending_screenshots = True
            self.watchdog.report_restart()
            return True
        return True  # No clients = no stream needed = success

    async def _validate_stream(self) -> bool:
        """Validate that stream is healthy."""
        if len(self.streaming_clients) == 0:
            return True  # No clients = nothing to validate
        return self.watchdog.is_healthy

    async def _restore_session_handler(self) -> bool:
        """Re-register agent on server after reconnect."""
        if not self.ws or not hasattr(self.ws, 'open') or not self.ws.open:
            return False
        try:
            register_msg = {
                "type": "register_agent",
                "data": {
                    "computer_id": self.computer_id,
                    "session_id": self.session_id,
                    "session_token": self.session_token,
                    "agent_id": self.hostname,
                    "hostname": self.hostname,
                },
            }
            await self.ws.send(json.dumps(register_msg))
            self.diag_logger.info("session_restored", "Agent re-registered on server")
            return True
        except Exception as exc:
            self.diag_logger.error("session_restore_failed", f"Failed to restore session: {exc}")
            return False

    async def _validate_session(self) -> bool:
        """Check if agent is considered registered by the server."""
        return self.is_connected

    async def _restart_tasks_handler(self) -> bool:
        """Restart all background tasks."""
        self.diag_logger.info("restart_tasks", "Restarting background tasks")
        self._cancel_diagnostics_tasks()
        await asyncio.sleep(0.5)
        self._start_diagnostics_tasks()
        return True

    async def _validate_tasks(self) -> bool:
        """Validate that all tasks are running."""
        return self.heartbeat.is_running

    # ─── Stall handler ───────────────────────────────────────────────

    async def _on_screenshot_stall(self) -> None:
        """Called by watchdog when screenshot stall is detected."""
        self.event_store.add_event(
            component="screenshot_watchdog",
            event="screenshot_stall",
            severity=Severity.WARNING,
            details=self.watchdog.get_stats(),
            agent_id=self.hostname,
        )

        # Try recovery: restart stream
        if len(self.streaming_clients) > 0:
            result = await self.recovery_mgr.execute_recovery(RecoveryAction.RESTART_STREAM)
            if not result.fully_successful:
                self.diag_logger.error(
                    "stream_recovery_failed",
                    f"Screenshot stream recovery failed: {result.details}",
                )
                # Escalate: try full reconnect
                self.fsm.transition(AgentState.DEGRADED)
            else:
                self.diag_logger.info(
                    "stream_recovered",
                    "Screenshot stream recovered after stall",
                )

    # ─── Task management ─────────────────────────────────────────────

    def _start_diagnostics_tasks(self) -> None:
        """Start all diagnostics background tasks."""
        if not self.loop:
            return

        # Heartbeat
        self.heartbeat.set_sender(self._ws_safe_send)
        hb_task = asyncio.create_task(self.heartbeat.start())
        self.diagnostics_tasks.append(hb_task)

        # Watchdog
        wd_task = asyncio.create_task(self.watchdog.run())
        self.diagnostics_tasks.append(wd_task)

        # Send diagnostics events periodically
        diag_send_task = asyncio.create_task(self._send_diagnostics_periodically())
        self.diagnostics_tasks.append(diag_send_task)

        self.diag_logger.info("diagnostics_started", "All diagnostics tasks started")

    def _cancel_diagnostics_tasks(self) -> None:
        """Cancel all diagnostics tasks."""
        for task in self.diagnostics_tasks:
            if task and not task.done():
                task.cancel()
        self.diagnostics_tasks.clear()

    async def _stop_diagnostics_tasks(self) -> None:
        """Gracefully stop all diagnostics subsystems."""
        await self.heartbeat.stop()
        await self.watchdog.stop()
        self._cancel_diagnostics_tasks()

    async def _ws_safe_send(self, payload: str) -> None:
        """Thread-safe ws.send wrapper."""
        if self.ws and hasattr(self.ws, 'open') and self.ws.open:
            try:
                await self.ws.send(payload)
            except Exception as exc:
                self.diag_logger.error("ws_send_failed", f"WS send failed: {exc}")

    # ─── Diagnostics event sending ───────────────────────────────────

    async def _send_diagnostics_periodically(self) -> None:
        """Periodically send cached diagnostic events to server."""
        last_sent = 0.0
        while self.is_running:
            try:
                await asyncio.sleep(DIAGNOSTIC_SEND_INTERVAL)
                if not self.is_running:
                    break
                events = self.event_store.get_pending(since=last_sent)
                if events and self.ws and hasattr(self.ws, 'open') and self.ws.open:
                    for ev in events:
                        msg = ev.to_ws_message()
                        await self._ws_safe_send(json.dumps(msg))
                    last_sent = time.time()
                # Trim stale events
                self.event_store.get_pending(since=time.time() - 3600)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.diag_logger.error("diag_send_error", f"Failed to send diagnostic events: {exc}")
                await asyncio.sleep(10)

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
        
        self.stop(close_session=True)
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
                            action_type = action_info.get('action_type', 'restart')
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
            self.event_store.add_event(
                component="system",
                event="shutdown_handler_error",
                severity=Severity.ERROR,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
    
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
                
                # 1. Переключаем JSON логгер на новый день
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
                await asyncio.sleep(60)
    
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
            except Exception:
                self.diag_logger.error("urgent_upload_error", "Failed to upload urgent files")
                await asyncio.sleep(60)

    # ─── Recovery pipeline (self-healing) ────────────────────────────

    async def _recovery_pipeline(self) -> bool:
        """Full recovery pipeline after disconnect.

        Recovery flow:
            RECOVERING -> reconnect websocket -> restore session
            -> restart stream -> restart tasks -> STREAMING/REGISTERED
        """
        self.fsm.transition(AgentState.RECOVERING)
        self.diag_logger.info("recovery_pipeline_started", "Starting full recovery pipeline")

        pipeline_actions = [
            RecoveryAction.RECONNECT_WEBSOCKET,
            RecoveryAction.RESTORE_SESSION,
            RecoveryAction.RESTART_TASKS,
        ]

        # If there were clients streaming, add stream restart
        if len(self.streaming_clients) > 0:
            pipeline_actions.insert(2, RecoveryAction.RESTART_STREAM)

        results = await self.recovery_mgr.execute_recovery_pipeline(pipeline_actions)

        # Check final result
        all_ok = all(
            r.success for r in results.values()
        )

        if all_ok:
            self.fsm.transition(AgentState.REGISTERED)
            self._consecutive_errors = 0
            self.diag_logger.info("recovery_complete", "Full recovery pipeline completed successfully")
            return True
        else:
            failed_actions = [
                k for k, v in results.items() if not v.success
            ]
            self.event_store.add_event(
                component="recovery",
                event="recovery_failed",
                severity=Severity.ERROR,
                details={"failed_actions": failed_actions, "results": {k: v.to_dict() for k, v in results.items()}},
                agent_id=self.hostname,
            )
            # Reset to DISCONNECTED so next iteration can attempt CONNECTING
            self.fsm.force_transition(AgentState.DISCONNECTED)
            self._consecutive_errors += 1
            self.diag_logger.error(
                "recovery_failed",
                f"Recovery pipeline failed on: {', '.join(failed_actions)}",
            )
            return False

    # ─── Agent main loop with self-healing ───────────────────────────

    async def agent_main(self):
        """Main agent loop with WebSocket self-healing recovery."""
        reconnect_delay = RECONNECT_BASE_DELAY

        # Инициализация аудио устройства
        try:
            import sounddevice as sd
            sd.default.device[1]
        except ImportError:
            pass

        await self.check_and_upload_on_startup()
        await self.collect_initial_metrics_and_events()

        # Проверяем, не нужно ли создать файл для сегодняшнего дня
        current_date = datetime.now().date()
        if self.json_logger.current_date != current_date:
            self.log_message.emit(f"📅 Обнаружено несоответствие дат: логгер={self.json_logger.current_date}, текущая={current_date}")
            self.json_logger.switch_to_new_day()

        tasks = [
            asyncio.create_task(self.collect_metrics_periodically()),
            asyncio.create_task(self.collect_new_windows_events_periodically()),
            asyncio.create_task(self.update_activity_periodically()),
            asyncio.create_task(self.check_and_upload_at_midnight()),
            asyncio.create_task(self.check_urgent_upload()),
        ]

        self.loop = asyncio.get_running_loop()

        # Start diagnostics tasks
        self._start_diagnostics_tasks()

        while self.is_running:
            try:
                # ── CONNECTING state ──
                self.fsm.transition(AgentState.CONNECTING)
                self.log_message.emit(f"🔄 Подключение к серверу: {self.relay_server}")
                self.diag_logger.info("connecting", f"Connecting to {self.relay_server}")

                async with websockets.connect(
                    self.relay_server,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.fsm.transition(AgentState.REGISTERED)

                    # Register on server
                    register_msg = {
                        "type": "register_agent",
                        "data": {
                            "computer_id": self.computer_id,
                            "session_id": self.session_id,
                            "session_token": self.session_token,
                            "agent_id": self.hostname,
                            "hostname": self.hostname,
                        },
                    }
                    await ws.send(json.dumps(register_msg))
                    self.log_message.emit(f"✅ Зарегистрирован на сервере")

                    # Update senders for ACK and heartbeat (heartbeat already running from _start_diagnostics_tasks)
                    self.ack_sender.set_sender(self._ws_safe_send)
                    self.heartbeat.set_sender(self._ws_safe_send)

                    self.connection_status_changed.emit(True, self.connected_clients)
                    self._consecutive_errors = 0

                    # Receive and process commands (blocking)
                    await self.receive_commands(ws)

            except websockets.ConnectionClosedError as e:
                self.event_store.add_event(
                    component="ws",
                    event="connection_closed",
                    severity=Severity.WARNING,
                    details={"code": getattr(e, 'code', 'unknown'), "reason": getattr(e, 'reason', 'unknown')},
                    agent_id=self.hostname,
                )
                self.log_message.emit(f"⚠️ Соединение закрыто: {e}")
            except websockets.ConnectionClosedOK:
                self.log_message.emit("ℹ️ Соединение закрыто штатно")
            except OSError as e:
                self.event_store.add_event(
                    component="ws",
                    event="connection_os_error",
                    severity=Severity.ERROR,
                    details={"error": str(e)},
                    agent_id=self.hostname,
                )
                self.log_message.emit(f"❌ Ошибка сети: {e}")
            except asyncio.CancelledError:
                self.log_message.emit("ℹ️ Задача отменена")
                break
            except Exception as e:
                self.event_store.add_event(
                    component="ws",
                    event="connection_error",
                    severity=Severity.ERROR,
                    details={"error": str(e)},
                    agent_id=self.hostname,
                )
                self.log_message.emit(f"❌ Ошибка подключения: {e}")
                import traceback
                self.log_message.emit(traceback.format_exc())

            # ── Disconnected state ──
            self.is_connected = False
            self.ws = None
            self.connection_status_changed.emit(False, 0)

            if not self.is_running:
                break

            # ── Run recovery pipeline ──
            self.fsm.force_transition(AgentState.DISCONNECTED)
            recovered = await self._recovery_pipeline()

            if not recovered:
                # Apply exponential backoff
                backoff = min(
                    reconnect_delay * (2 ** min(self._consecutive_errors, 5)),
                    120.0,
                )
                self.log_message.emit(
                    f"⏳ Ожидание {backoff:.0f}с перед повторным подключением "
                    f"(попытка {self._consecutive_errors})"
                )
                await asyncio.sleep(backoff)
            else:
                # Short delay before re-entering the loop to reconnect
                await asyncio.sleep(1)

        # ── Cleanup ──
        self.diag_logger.info("agent_stopping", "Agent main loop exiting, cleaning up tasks")
        await self._stop_diagnostics_tasks()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.diag_logger.info("agent_stopped", "Agent main loop exited")
    
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
        import sounddevice as sd

        self.sending_audio = True

        try:
            hostapis = sd.query_hostapis()
            devices = sd.query_devices()

            wasapi_index = None

            # 🔍 ищем WASAPI
            for i, api in enumerate(hostapis):
                if "wasapi" in api['name'].lower():
                    wasapi_index = i
                    break

            if wasapi_index is None:
                self.log_message.emit("❌ WASAPI не найден")
                return

            self.log_message.emit("✅ Используем WASAPI")

            # 🔥 ищем output device с WASAPI
            target_device = None

            for i, dev in enumerate(devices):
                if dev['hostapi'] == wasapi_index and dev['max_output_channels'] > 0:
                    target_device = i
                    break

            if target_device is None:
                self.log_message.emit("❌ WASAPI устройство не найдено")
                return

            self.log_message.emit(f"🎧 DEVICE: {devices[target_device]['name']}")

            sample_rate = int(devices[target_device]['default_samplerate'])
            channels = 2

            loop = asyncio.get_running_loop()

            def callback(indata, frames, time, status):
                if not self.sending_audio:
                    return

                try:
                    audio_bytes = indata.tobytes()

                    audio_b64 = base64.b64encode(audio_bytes).decode()

                    asyncio.run_coroutine_threadsafe(
                        ws.send(json.dumps({
                            "type": "audio_chunk",
                            "data": audio_b64,
                            "computer_id": self.computer_id,
                            "agent_id": self.hostname,
                            "sample_rate": sample_rate,
                            "channels": channels
                        })),
                        loop
                    )
                except Exception as exc:
                    self.event_store.add_event(
                        component="audio",
                        event="audio_callback_error",
                        severity=Severity.ERROR,
                        details={"error": str(exc)},
                        agent_id=self.hostname,
                    )

            # 🔥 ВАЖНО: loopback через extra_settings
            wasapi_settings = sd.WasapiSettings()

            with sd.InputStream(
                samplerate=sample_rate,
                device=target_device,
                channels=channels,
                callback=callback,
                dtype='int16',
                extra_settings=wasapi_settings
            ):
                self.log_message.emit("✅ AUDIO LOOPBACK STARTED")

                while self.sending_audio and len(self.streaming_clients) > 0:
                    await asyncio.sleep(0.1)

        except Exception as e:
            self.log_message.emit(f"❌ AUDIO ERROR: {e}")

        self.sending_audio = False
    
    async def screenshot_loop(self, ws):
        """Захват и трансляция скриншотов экрана"""
        self.sending_screenshots = True
        error_count = 0
        max_errors = 5
        
        # Notify watchdog that streaming has started
        self.watchdog.start_streaming()
        
        while self.sending_screenshots and self.is_connected and self.is_running and len(self.streaming_clients) > 0:
            try:
                start_time = time.time()
                
                img = self._take_screenshot()
                
                if img is None:
                    error_count += 1
                    if error_count >= max_errors:
                        self.log_message.emit(f"Слишком много ошибок скриншота ({max_errors}), остановка")
                        self.event_store.add_event(
                            component="screenshot",
                            event="screenshot_loop_stopped",
                            severity=Severity.ERROR,
                            details={"error_count": error_count, "reason": "max_errors_exceeded"},
                            agent_id=self.hostname,
                        )
                        break
                    await asyncio.sleep(1)
                    continue
                
                # Report frame to watchdog
                self.watchdog.report_frame()
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
                    
            except websockets.ConnectionClosedError:
                self.log_message.emit("⚠️ Соединение закрыто во время трансляции")
                break
            except websockets.ConnectionClosedOK:
                break
            except Exception as e:
                self.log_message.emit(f"Ошибка в screenshot_loop: {e}")
                self.event_store.add_event(
                    component="screenshot",
                    event="screenshot_loop_error",
                    severity=Severity.ERROR,
                    details={"error": str(e)},
                    agent_id=self.hostname,
                )
                error_count += 1
                if error_count >= max_errors:
                    break
                await asyncio.sleep(1)
        
        self.sending_screenshots = False
        self.watchdog.stop_streaming()
        self.diag_logger.info(
            "screenshot_loop_ended",
            "Screenshot loop ended",
            {"frames": self.watchdog.frames_received, "stalls": self.watchdog.stall_count},
        )
    
    async def receive_commands(self, ws):
        """Получение и обработка команд от сервера"""
        screenshot_task = None
        audio_task = None
        
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                client_id = data.get("client_id") or data.get("data", {}).get("client_id", "unknown")
                
                # ── ACK protocol: if command has command_id, send ACK ──
                command_id = data.get("command_id")
                if command_id:
                    asyncio.create_task(self.ack_sender.send_ack(command_id))
                
                if cmd_type == "register_client":
                    if client_id not in self.connected_clients_list:
                        self.connected_clients += 1
                        self.connected_clients_list.append(client_id)
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_connected.emit(client_id)
                        self.log_message.emit(f"👤 Клиент {client_id} подключен")
                
                elif cmd_type == "start_stream":
                    self.streaming_clients.add(client_id)
                    self.log_message.emit(f"🎬 Трансляция для {client_id} запущена")
                    
                    # Запускаем только видео трансляцию
                    if not self.sending_screenshots and len(self.streaming_clients) > 0:
                        if screenshot_task is None or screenshot_task.done():
                            screenshot_task = asyncio.create_task(self.screenshot_loop(ws))
                
                elif cmd_type == "stop_stream":
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                        self.log_message.emit(f"⏹️ Трансляция для {client_id} остановлена")
                    
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                        self.sending_audio = False
                        
                        if screenshot_task and not screenshot_task.done():
                            screenshot_task.cancel()
                        
                        if audio_task and not audio_task.done():
                            audio_task.cancel()
                
                elif cmd_type == "start_audio":
                    if (audio_task is None or audio_task.done()):
                        audio_task = asyncio.create_task(self.audio_capture_loop(ws))
                        self.log_message.emit(f"🎧 Аудио запущено")
                
                elif cmd_type == "stop_audio":
                    self.sending_audio = False
                    if audio_task and not audio_task.done():
                        audio_task.cancel()
                        self.log_message.emit(f"🔇 Аудио остановлено")
                
                elif cmd_type == "unregister_client":
                    if client_id in self.connected_clients_list:
                        self.connected_clients_list.remove(client_id)
                        self.connected_clients = max(0, self.connected_clients - 1)
                        self.connection_status_changed.emit(True, self.connected_clients)
                        self.client_disconnected.emit(client_id)
                        self.log_message.emit(f"👋 Клиент {client_id} отключен")
                    
                    if client_id in self.streaming_clients:
                        self.streaming_clients.remove(client_id)
                    
                    if len(self.streaming_clients) == 0:
                        self.sending_screenshots = False
                        self.sending_audio = False
                        
                        if screenshot_task and not screenshot_task.done():
                            screenshot_task.cancel()
                        if audio_task and not audio_task.done():
                            audio_task.cancel()
                
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
                
        except json.JSONDecodeError as e:
            self.log_message.emit(f"⚠️ Ошибка декодирования JSON: {e}")
            self.event_store.add_event(
                component="commands",
                event="json_decode_error",
                severity=Severity.WARNING,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
        except websockets.ConnectionClosedError as e:
            self.log_message.emit(f"⚠️ Соединение закрыто: {e}")
            raise  # Let agent_main handle reconnection
        except Exception as e:
            self.log_message.emit(f"Ошибка в receive_commands: {e}")
            import traceback
            self.log_message.emit(traceback.format_exc())
            self.event_store.add_event(
                component="commands",
                event="receive_commands_error",
                severity=Severity.ERROR,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
        finally:
            if screenshot_task and not screenshot_task.done():
                screenshot_task.cancel()
            if audio_task and not audio_task.done():
                audio_task.cancel()
            self.sending_screenshots = False
            self.sending_audio = False
    
    async def handle_mouse_move(self, command_data):
        try:
            x = command_data.get("x")
            y = command_data.get("y")
            if x is not None and y is not None:
                self.mouse.position = (x, y)
        except Exception as e:
            self.event_store.add_event(
                component="input",
                event="mouse_move_error",
                severity=Severity.WARNING,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
    
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
        except Exception as e:
            self.event_store.add_event(
                component="input",
                event="mouse_click_error",
                severity=Severity.WARNING,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
    
    async def handle_mouse_wheel(self, command_data):
        try:
            delta = command_data.get("delta", 0)
            self.mouse.scroll(0, delta)
        except Exception as e:
            self.event_store.add_event(
                component="input",
                event="mouse_wheel_error",
                severity=Severity.WARNING,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
    
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
                else:
                    self.keyboard.type(text)
        except Exception as e:
            self.event_store.add_event(
                component="input",
                event="keyboard_input_error",
                severity=Severity.WARNING,
                details={"error": str(e)},
                agent_id=self.hostname,
            )
    
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
    
    def stop(self, close_session: bool = False):
        """Останавливает работу агента
        
        Args:
            close_session: Закрывать ли сессию (True - при выходе, False - при переподключении)
        """
        self.log_message.emit("🛑 Остановка агента...")
        self.is_running = False
        self.is_connected = False
        self.sending_screenshots = False
        self.sending_audio = False
        self.streaming_clients.clear()
        self.connected_clients_list.clear()
        
        # Stop diagnostics subsystems
        if hasattr(self, 'loop') and self.loop and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._stop_diagnostics_tasks(),
                    self.loop,
                )
            except Exception:
                self.diag_logger.error("stop_error", "Failed to stop diagnostics tasks during shutdown")
        
        # Закрываем сессию только если явно указано
        if close_session:
            self.close_session()
        
        # Обновляем статус компьютера на офлайн
        try:
            APIClient.update_computer_status(self.computer_id, False, self.session_id)
            self.log_message.emit(f"✅ Статус компьютера обновлен на офлайн")
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
        
        # Кнопки управления
        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        
        self.reconnect_btn = QPushButton("🔄 Переподключиться")
        self.reconnect_btn.setFixedWidth(150)
        self.reconnect_btn.clicked.connect(self.reconnect)
        control_layout.addWidget(self.reconnect_btn)
        
        control_layout.addStretch()
        
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
        control_layout.addWidget(self.exit_btn)
        
        main_layout.addWidget(control_frame)
        
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
        
        reconnect_action = QAction("🔄 Переподключиться", self)
        reconnect_action.triggered.connect(self.reconnect)
        tray_menu.addAction(reconnect_action)
        
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
            self.add_to_startup_on_first_run()
        
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
            except Exception:
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
            except Exception:
                pass
            winreg.CloseKey(key)
            
            startup_script = os.path.join(os.environ.get("APPDATA", ""), 
                                          r"Microsoft\Windows\Start Menu\Programs\Startup",
                                          "remote_access_agent_start.bat")
            if os.path.exists(startup_script):
                os.remove(startup_script)
            self.log("✅ Удалено из автозагрузки Windows")
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
                self.log("✅ Удалено из автозагрузки Linux")
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
    
    def reconnect(self):
        """Переподключение к серверу без закрытия сессии"""
        if self.agent_thread:
            if self.agent_thread.is_connected:
                self.log("🔄 Переподключение к серверу...")
                self.agent_thread.is_running = False
                self.agent_thread.is_connected = False
                if self.agent_thread.ws:
                    asyncio.run_coroutine_threadsafe(
                        self.agent_thread.ws.close(),
                        self.agent_thread.loop
                    )
                self.agent_thread.wait(2000)
            else:
                self.log("🔄 Подключение к серверу...")
        
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
            self.log("✅ Подключен к серверу")
            self.status_bar.showMessage("Подключен к серверу")
            
            if self.tray_icon:
                self.tray_icon.setToolTip("Remote Access Agent - Подключен")
                self.tray_icon.showMessage(
                    "Remote Access Agent",
                    "Подключен к серверу",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        else:
            self.status_label.setText("● Не подключен")
            self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
            self.status_bar.showMessage("Отключен от сервера")
            
            if self.tray_icon:
                self.tray_icon.setToolTip("Remote Access Agent - Отключен")
    
    def on_client_connected(self, client_id):
        self.log(f"👤 Клиент {client_id} подключился")
        if self.tray_icon:
            self.tray_icon.showMessage(
                "Новое подключение",
                f"Клиент {client_id} подключился",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def on_client_disconnected(self, client_id):
        self.log(f"👋 Клиент {client_id} отключился")
    
    def quit_application(self):
        reply = QMessageBox.question(
            self, "Подтверждение", "Вы уверены, что хотите выйти?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            session_id = self.computer_data.get('session_id')
            if session_id:
                print(f"[MAIN] Завершение работы, закрываем сессию {session_id}...")
                try:
                    DatabaseManager.close_session_by_id(session_id)
                    print(f"[MAIN] ✅ Сессия {session_id} закрыта")
                except Exception as e:
                    print(f"[MAIN] ❌ Ошибка закрытия сессии: {e}")
            
            if self.agent_thread:
                self.agent_thread.stop(close_session=False)
                self.agent_thread.wait(3000)
            
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            
            if self.tray_icon:
                self.tray_icon.hide()
            
            QApplication.quit()
    
    def closeEvent(self, event):
        if self.minimize_to_tray and self.tray_icon and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Remote Access Agent",
                "Приложение свернуто в трей",
                QSystemTrayIcon.MessageIcon.Information,
                1000
            )
        else:
            session_id = self.computer_data.get('session_id')
            if session_id:
                print(f"[MAIN] Закрытие окна, закрываем сессию {session_id}...")
                try:
                    DatabaseManager.close_session_by_id(session_id)
                except Exception as e:
                    print(f"[MAIN] Ошибка закрытия сессии: {e}")
            
            if self.agent_thread:
                self.agent_thread.stop(close_session=False)
                self.agent_thread.wait(3000)
            
            if self.computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    self.computer_data['computer_id'], False,
                    self.computer_data.get('session_id')
                )
            
            if self.tray_icon:
                self.tray_icon.hide()
            
            event.accept()
