"""Основное окно детальной информации о компьютере"""

import sys
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QFrame, QTabWidget, QMessageBox, QDialog)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from core.api_client import APIClient
from .widgets import DateRangeWidget, get_app_icon
from .overview_tab import OverviewTab
from .metrics_tab import MetricsTab
from .events_tab import EventsTab
from .sessions_tab import SessionsTab
from .anomalies_tab import AnomaliesTab
from .reports_tab import ReportsTab
from .dialogs import EditComputerDialog
from ..styles import get_main_window_stylesheet


class ComputerDetailsWindow(QMainWindow):
    """Окно с детальной информацией по компьютеру"""
    
    def __init__(self, hostname, computer_data):
        super().__init__()
        self.hostname = hostname
        self.computer_data = computer_data
        self.current_data = None
        self.computer_id = None
        self.current_disk_info = {'used_gb': None, 'total_gb': None}
        self.admin_panel = None  # Сохраняем ссылку на админ-панель
        
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
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        remote_btn = QPushButton("🖥️ Удаленный экран")
        remote_btn.setFixedWidth(150)
        remote_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                border-radius: 6px;
                padding: 5px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        remote_btn.clicked.connect(self.open_remote_screen)
        btn_layout.addWidget(remote_btn)
        
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
        btn_layout.addWidget(edit_btn)
        
        header_layout.addLayout(btn_layout)
        header_layout.setAlignment(btn_layout, Qt.AlignmentFlag.AlignRight)
        
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
    
    def go_back(self):
        """Возврат к админ-панели"""
        from ..admin_panel import AdminPanelWindow
        # Создаем новое окно админ-панели с данными пользователя
        user_data = {
            'login': self.computer_data.get('user_login', 'Admin'),
            'computer_id': None,
            'session_id': None,
            'role_id': 2
        }
        self.admin_panel = AdminPanelWindow(user_data)
        self.admin_panel.show()
        self.close()
    
    def open_remote_screen(self):
        """Открывает окно удаленного доступа к компьютеру"""
        if not self.computer_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера не определен")
            return
            
        try:
            import json
            import asyncio
            import websockets
            from PIL import Image
            from io import BytesIO
            import base64
            import time
            
            from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                        QLabel, QLineEdit, QPushButton, QFrame, QMessageBox,
                                        QSizePolicy)
            from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
            from PyQt6.QtGui import QPixmap, QImage, QFont
            
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
                    self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    self.setFocus()
                
                def set_screen_size(self, width, height):
                    self.host_screen_width = width
                    self.host_screen_height = height
                    
                def get_image_coords(self, widget_x, widget_y):
                    pixmap = self.pixmap()
                    if pixmap:
                        img_left = (self.width() - pixmap.width()) // 2
                        img_right = img_left + pixmap.width()
                        img_top = (self.height() - pixmap.height()) // 2
                        img_bottom = img_top + pixmap.height()
                        
                        if (img_left <= widget_x <= img_right and 
                            img_top <= widget_y <= img_bottom):
                            img_x = widget_x - img_left
                            img_y = widget_y - img_top
                            
                            scale_x = self.host_screen_width / pixmap.width()
                            scale_y = self.host_screen_height / pixmap.height()
                            
                            host_x = int(img_x * scale_x)
                            host_y = int(img_y * scale_y)
                            
                            host_x = max(0, min(host_x, self.host_screen_width - 1))
                            host_y = max(0, min(host_y, self.host_screen_height - 1))
                            
                            return img_x, img_y, host_x, host_y
                    return None, None, None, None
                
                def mouseMoveEvent(self, event):
                    if self.host_screen_width and self.host_screen_height:
                        img_x, img_y, host_x, host_y = self.get_image_coords(
                            int(event.position().x()), 
                            int(event.position().y())
                        )
                        if img_x is not None:
                            self.mouse_moved.emit(img_x, img_y, host_x, host_y)
                
                def mousePressEvent(self, event):
                    if self.host_screen_width and self.host_screen_height:
                        img_x, img_y, host_x, host_y = self.get_image_coords(
                            int(event.position().x()), 
                            int(event.position().y())
                        )
                        if img_x is not None:
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
                    super().keyPressEvent(event)
            
            class RemoteClientThread(QThread):
                image_received = pyqtSignal(object, int, int)
                connection_status = pyqtSignal(str)
                
                def __init__(self, computer_id):
                    super().__init__()
                    self.computer_id = computer_id
                    self.is_running = True
                    self.command_queue = asyncio.Queue()
                
                def run(self):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self.client_loop())
                    finally:
                        loop.close()
                
                async def client_loop(self):
                    while self.is_running:
                        try:
                            async with websockets.connect("ws://130.49.149.152:9001") as websocket:
                                from core.api_client import APIClient
                                await websocket.send(json.dumps({
                                    "type": "register_client",
                                    "computer_id": self.computer_id,
                                    "client_id": f"ADMIN_{int(time.time())}",
                                    "user_id": APIClient.auth_token
                                }))
                                await websocket.send(json.dumps({"type": "start_stream", "computer_id": self.computer_id}))
                                self.connection_status.emit("Подключено")
                                
                                send_task = asyncio.create_task(self.process_commands(websocket))
                                
                                async for msg in websocket:
                                    if not self.is_running:
                                        break
                                    try:
                                        data = json.loads(msg)
                                        if data.get("type") == "screenshot":
                                            img_data = base64.b64decode(data["data"])
                                            img = Image.open(BytesIO(img_data))
                                            screen_w = data.get("screen_width", img.width)
                                            screen_h = data.get("screen_height", img.height)
                                            self.image_received.emit(img, screen_w, screen_h)
                                    except:
                                        pass
                        except Exception as e:
                            self.connection_status.emit(f"Ошибка: {str(e)}")
                        if self.is_running:
                            await asyncio.sleep(2)
                
                async def process_commands(self, websocket):
                    while self.is_running:
                        try:
                            cmd = await asyncio.wait_for(self.command_queue.get(), timeout=0.1)
                            await websocket.send(json.dumps(cmd))
                        except asyncio.TimeoutError:
                            pass
                
                def send_command(self, cmd):
                    if self.is_running:
                        asyncio.run_coroutine_threadsafe(self.command_queue.put(cmd), self.loop)
                
                def stop(self):
                    self.is_running = False
            
            class RemoteScreenWindow(QMainWindow):
                closed = pyqtSignal()
                
                def __init__(self, computer_id, computer_name):
                    super().__init__()
                    self.computer_id = computer_id
                    self.client_thread = RemoteClientThread(computer_id)
                    self.init_ui(computer_name)
                    
                    self.screen_widget.mouse_moved.connect(lambda ix,iy,hx,hy: 
                        self.client_thread.send_command({
                            "type": "mouse_move", "computer_id": computer_id, "data": {"x": hx, "y": hy}
                        }))
                    self.screen_widget.mouse_clicked.connect(lambda btn,hx,hy:
                        self.client_thread.send_command({
                            "type": "mouse_click", "computer_id": computer_id, "data": {"button": btn, "x": hx, "y": hy}
                        }))
                    self.screen_widget.mouse_wheeled.connect(lambda delta:
                        self.client_thread.send_command({
                            "type": "mouse_wheel", "computer_id": computer_id, "data": {"delta": delta}
                        }))
                    self.screen_widget.key_pressed.connect(lambda text:
                        self.client_thread.send_command({
                            "type": "keyboard_input", "computer_id": computer_id, "data": {"text": text}
                        }))
                    
                    self.client_thread.image_received.connect(self.update_image)
                    self.client_thread.connection_status.connect(self.status_label.setText)
                    self.client_thread.start()
                
                def init_ui(self, computer_name):
                    self.setWindowTitle(f"Удаленный экран | {computer_name}")
                    self.setGeometry(200, 200, 1280, 720)
                    
                    central = QWidget()
                    self.setCentralWidget(central)
                    layout = QVBoxLayout(central)
                    layout.setContentsMargins(0, 0, 0, 0)
                    
                    status_bar = QFrame()
                    status_bar.setStyleSheet("background-color: #2c3e50;")
                    status_bar.setFixedHeight(25)
                    status_layout = QHBoxLayout(status_bar)
                    status_layout.setContentsMargins(5, 0, 5, 0)
                    
                    self.status_label = QLabel("Подключение...")
                    self.status_label.setStyleSheet("color: white; font-size: 11px;")
                    status_layout.addWidget(self.status_label)
                    layout.addWidget(status_bar)
                    
                    self.screen_widget = RemoteScreenWidget()
                    self.screen_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                    layout.addWidget(self.screen_widget, 1)
                    
                    QTimer.singleShot(100, self.screen_widget.setFocus)
                
                def update_image(self, img, screen_w, screen_h):
                    widget_size = self.screen_widget.size()
                    if widget_size.width() <= 1 or widget_size.height() <= 1:
                        return
                    
                    self.screen_widget.set_screen_size(screen_w, screen_h)
                    img_ratio = img.width / img.height
                    widget_ratio = widget_size.width() / widget_size.height()
                    
                    if img_ratio > widget_ratio:
                        new_width = widget_size.width()
                        new_height = int(widget_size.width() / img_ratio)
                    else:
                        new_height = widget_size.height()
                        new_width = int(widget_size.height() * img_ratio)
                    
                    if new_width > 0 and new_height > 0:
                        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        img_byte_array = BytesIO()
                        img_resized.save(img_byte_array, format='PNG')
                        qimage = QImage.fromData(img_byte_array.getvalue())
                        self.screen_widget.setPixmap(QPixmap.fromImage(qimage))
                
                def closeEvent(self, event):
                    self.client_thread.stop()
                    self.closed.emit()
                    event.accept()
            
            self.remote_window = RemoteScreenWindow(self.computer_id, self.hostname)
            self.remote_window.show()
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось запустить удаленный экран: {str(e)}")
    
    def closeEvent(self, event):
        """Обработка закрытия окна - НЕ закрываем сессию, просто показываем админ-панель"""
        from ..admin_panel import AdminPanelWindow
        user_data = {
            'login': self.computer_data.get('user_login', 'Admin'),
            'computer_id': None,
            'session_id': None,
            'role_id': 2
        }
        self.admin_panel = AdminPanelWindow(user_data)
        self.admin_panel.show()
        event.accept()
