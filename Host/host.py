import asyncio
import websockets
import json
import mss
from io import BytesIO
from PIL import Image
import base64
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, messagebox
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController
import platform
import psutil
import socket
from datetime import datetime

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
                events.append({"event_type": "warning", "event_source": "cpu", "description": f"Высокая загрузка CPU: {cpu_usage}%", "severity_level": "medium"})
            if ram_usage > 90:
                events.append({"event_type": "warning", "event_source": "memory", "description": f"Высокое использование RAM: {ram_usage}%", "severity_level": "medium"})
            if disk_usage > 90:
                events.append({"event_type": "warning", "event_source": "disk", "description": f"Мало места на диске: {disk_usage}% использовано", "severity_level": "medium"})
            
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

class RemoteAccessHost:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Удалённый доступ - Хост")
        self.root.geometry("500x400")
        self.root.configure(bg='#f0f0f0')
        
        self.relay_server = tk.StringVar(value="ws://130.49.149.152:9001")
        self.host_id = tk.StringVar(value="PC_HOME")
        self.screenshot_interval = tk.DoubleVar(value=0.1)
        
        self.is_running = False
        self.is_connected = False
        self.connected_clients = 0
        
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
        
        self.ws = None
        self.loop = None
        self.create_ui()
    
    def create_ui(self):
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="ХОСТ УДАЛЕННОГО ДОСТУПА", 
                font=("Arial", 14, "bold"), fg='white', bg='#2c3e50').pack(pady=15)
        
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        status_frame = tk.LabelFrame(main_frame, text="Статус", font=("Arial", 10, "bold"), bg='#f0f0f0')
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_label = tk.Label(status_frame, text="ОСТАНОВЛЕН", font=("Arial", 10), fg='red', bg='#f0f0f0')
        self.status_label.pack(pady=2)
        self.clients_label = tk.Label(status_frame, text="Клиентов: 0", bg='#f0f0f0')
        self.clients_label.pack(pady=2)
        
        settings_frame = tk.LabelFrame(main_frame, text="Настройки", font=("Arial", 10, "bold"), bg='#f0f0f0')
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(settings_frame, text="Сервер:", bg='#f0f0f0').grid(row=0, column=0, sticky='w', pady=2)
        tk.Entry(settings_frame, textvariable=self.relay_server, width=30).grid(row=0, column=1, padx=5)
        
        tk.Label(settings_frame, text="ID хоста:", bg='#f0f0f0').grid(row=1, column=0, sticky='w', pady=2)
        tk.Entry(settings_frame, textvariable=self.host_id, width=30).grid(row=1, column=1, padx=5)
        
        control_frame = tk.Frame(main_frame, bg='#f0f0f0')
        control_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = tk.Button(control_frame, text="ЗАПУСТИТЬ", bg='#27ae60', fg='white',
                                 command=self.start_host, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(control_frame, text="ОСТАНОВИТЬ", bg='#e74c3c', fg='white',
                                command=self.stop_host, width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        log_frame = tk.LabelFrame(main_frame, text="Журнал", padx=5, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        settings_frame.columnconfigure(1, weight=1)
    
    def log(self, message):
        try:
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
            self.log_text.see(tk.END)
        except:
            pass
    
    def update_status(self):
        try:
            if self.is_running and self.is_connected:
                self.status_label.config(text="АКТИВЕН", fg='green')
                self.clients_label.config(text=f"Клиентов: {self.connected_clients}")
                self.start_btn.config(state=tk.DISABLED)
                self.stop_btn.config(state=tk.NORMAL)
            elif self.is_running:
                self.status_label.config(text="ПОДКЛЮЧЕНИЕ...", fg='orange')
                self.start_btn.config(state=tk.DISABLED)
                self.stop_btn.config(state=tk.NORMAL)
            else:
                self.status_label.config(text="ОСТАНОВЛЕН", fg='red')
                self.clients_label.config(text="Клиентов: 0")
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
        except:
            pass
    
    def start_host(self):
        if not self.relay_server.get().startswith('ws://'):
            messagebox.showerror("Ошибка", "Сервер должен начинаться с ws://")
            return
        if not self.host_id.get():
            messagebox.showerror("Ошибка", "Введите ID хоста")
            return
        
        self.is_running = True
        self.update_status()
        self.log("Запуск хоста...")
        
        host_thread = threading.Thread(target=self.run_host, daemon=True)
        host_thread.start()
    
    def stop_host(self):
        self.is_running = False
        self.is_connected = False
        self.connected_clients = 0
        if self.loop and self.ws:
            try:
                asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
            except:
                pass
        self.update_status()
        self.log("Хост остановлен")
    
    def run_host(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.host_main())
        except Exception as e:
            self.log(f"Ошибка: {e}")
            self.stop_host()
    
    async def host_main(self):
        reconnect_delay = 2
        while self.is_running:
            try:
                async with websockets.connect(self.relay_server.get()) as ws:
                    self.ws = ws
                    await ws.send(json.dumps({
                        "type": "register_host",
                        "data": {"host_id": self.host_id.get()},
                        "host_id": self.host_id.get()
                    }))
                    
                    self.is_connected = True
                    self.update_status()
                    self.log("Подключен к серверу")
                    
                    send_task = asyncio.create_task(self.send_loop(ws))
                    info_task = asyncio.create_task(self.info_loop(ws))
                    receive_task = asyncio.create_task(self.receive_commands(ws))
                    
                    await asyncio.wait([send_task, info_task, receive_task], return_when=asyncio.FIRST_COMPLETED)
                    
                    for task in [send_task, info_task, receive_task]:
                        task.cancel()
                    
            except Exception as e:
                self.log(f"Ошибка подключения: {e}")
            
            self.is_connected = False
            self.update_status()
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
            
            await ws.send(json.dumps({
                "type": "system_info",
                "data": system_info,
                "host_id": self.host_id.get()
            }))
            self.log("Информация о системе отправлена")
            return True
        except:
            return False
    
    async def info_loop(self, ws):
        await self.send_system_info(ws)
        last_sent = time.time()
        while self.is_running and self.is_connected:
            try:
                if time.time() - last_sent >= 3600:
                    await self.send_system_info(ws)
                    last_sent = time.time()
                await asyncio.sleep(60)
            except:
                break
    
    async def send_screenshot(self, ws):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=50)
                img_b64 = base64.b64encode(buffer.getvalue()).decode()
                
                await ws.send(json.dumps({
                    "type": "screenshot",
                    "data": img_b64,
                    "host_id": self.host_id.get()
                }))
                return True
        except:
            return False
    
    async def send_loop(self, ws):
        while self.is_running and self.is_connected:
            try:
                await self.send_screenshot(ws)
                await asyncio.sleep(self.screenshot_interval.get())
            except:
                break
    
    async def receive_commands(self, ws):
        try:
            async for msg in ws:
                data = json.loads(msg)
                cmd_type = data.get("type")
                
                if cmd_type == "register_client":
                    self.connected_clients += 1
                    self.update_status()
                    self.log("Клиент подключен")
                    await self.send_system_info(ws)
                
                elif cmd_type == "request_system_info":
                    await self.send_system_info(ws)
                
                elif cmd_type in ["mouse_move", "mouse_click", "key_press", "mouse_wheel", "command"]:
                    await self.handle_command(data.get("data", {}))
        except:
            pass
    
    async def handle_command(self, command):
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
                self.mouse.scroll(0, command.get("delta", 0))
            elif action == "key_press":
                key = command.get("key")
                if key in self.KEY_MAPPING:
                    self.keyboard.press(self.KEY_MAPPING[key])
                    self.keyboard.release(self.KEY_MAPPING[key])
            elif action == "text_input":
                self.keyboard.type(command.get("text", ""))
        except:
            pass
    
    def run(self):
        self.log("Хост запущен")
        self.root.mainloop()

if __name__ == "__main__":
    app = RemoteAccessHost()
    app.run()