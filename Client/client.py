import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import asyncio
import websockets
import json
import base64
from io import BytesIO
import threading
import time
import queue
from datetime import datetime

class RemoteAccessClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Удалённый доступ - Настройки")
        self.root.geometry("400x350")
        self.root.configure(bg='#f0f0f0')
        
        self.relay_server = tk.StringVar(value="ws://130.49.149.152:9001")
        self.host_id = tk.StringVar(value="PC_HOME")
        self.client_id = tk.StringVar(value="CLIENT")
        self.screen_update_interval = tk.DoubleVar(value=0.033)
        
        self.is_connected = False
        self.is_running = False
        
        self.create_ui()
    
    def create_ui(self):
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="УДАЛЕННЫЙ ДОСТУП", 
                font=("Arial", 14, "bold"), fg='white', bg='#2c3e50').pack(pady=15)
        
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        settings_frame = tk.LabelFrame(main_frame, text="Настройки", font=("Arial", 10, "bold"), bg='#f0f0f0')
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(settings_frame, text="Сервер:", bg='#f0f0f0').grid(row=0, column=0, sticky='w', pady=2)
        tk.Entry(settings_frame, textvariable=self.relay_server, width=30).grid(row=0, column=1, padx=5)
        
        tk.Label(settings_frame, text="ID хоста:", bg='#f0f0f0').grid(row=1, column=0, sticky='w', pady=2)
        tk.Entry(settings_frame, textvariable=self.host_id, width=30).grid(row=1, column=1, padx=5)
        
        tk.Label(settings_frame, text="ID клиента:", bg='#f0f0f0').grid(row=2, column=0, sticky='w', pady=2)
        tk.Entry(settings_frame, textvariable=self.client_id, width=30).grid(row=2, column=1, padx=5)
        
        button_frame = tk.Frame(main_frame, bg='#f0f0f0')
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = tk.Button(button_frame, text="ПОДКЛЮЧИТЬСЯ", bg='#27ae60', fg='white',
                                 command=self.start_client, width=20, height=2)
        self.start_btn.pack(pady=5)
        
        self.stop_btn = tk.Button(button_frame, text="ОТКЛЮЧИТЬСЯ", bg='#e74c3c', fg='white',
                                command=self.stop_client, width=15, state=tk.DISABLED)
        self.stop_btn.pack(pady=2)
        
        self.status_label = tk.Label(main_frame, text="Отключено", fg='red', bg='#f0f0f0')
        self.status_label.pack(pady=5)
        
        settings_frame.columnconfigure(1, weight=1)
    
    def start_client(self):
        if not self.relay_server.get().startswith('ws://'):
            messagebox.showerror("Ошибка", "Сервер должен начинаться с ws://")
            return
        if not self.host_id.get():
            messagebox.showerror("Ошибка", "Введите ID хоста")
            return
        
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Подключение...", fg='orange')
        
        self.is_running = True
        client_thread = threading.Thread(target=self.run_client, daemon=True)
        client_thread.start()
    
    def stop_client(self):
        self.is_running = False
        self.is_connected = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Отключено", fg='red')
    
    def run_client(self):
        try:
            client = RemoteClient(
                relay_server=self.relay_server.get(),
                host_id=self.host_id.get(),
                client_id=self.client_id.get(),
                update_interval=self.screen_update_interval.get(),
                status_callback=self.update_status
            )
            client.run()
        except Exception as e:
            self.update_status(f"Ошибка: {e}", "error")
    
    def update_status(self, message, message_type="info"):
        def update_ui():
            colors = {"info": "black", "success": "green", "error": "red", "warning": "orange"}
            color = colors.get(message_type, "black")
            self.status_label.config(text=message, fg=color)
            if "Подключено" in message:
                self.is_connected = True
            elif "Отключено" in message:
                self.is_connected = False
        self.root.after(0, update_ui)
    
    def run(self):
        self.root.mainloop()


class RemoteClient:
    def __init__(self, relay_server, host_id, client_id, update_interval, status_callback):
        self.relay_server = relay_server
        self.host_id = host_id
        self.client_id = client_id
        self.update_interval = update_interval
        self.status_callback = status_callback
        
        self.ws = None
        self.loop = None
        self.root = None
        self.host_screen_width = None
        self.host_screen_height = None
        self.command_queue = queue.Queue()
        self.is_connected = False
        self.frame_count = 0
        self.last_fps_update = 0
        
        self.host_info = {"basic": {}, "hardware": {}, "metrics": {}, "last_update": None}
        
        self.create_ui()
    
    def create_ui(self):
        self.root = tk.Toplevel()
        self.root.title(f"Удалённый доступ - {self.host_id}")
        self.root.geometry("900x650")
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.screen_tab = tk.Frame(self.notebook, bg='black')
        self.notebook.add(self.screen_tab, text="Удаленный экран")
        
        self.info_tab = tk.Frame(self.notebook, bg='#f0f0f0')
        self.notebook.add(self.info_tab, text="Информация о хосте")
        
        self.create_screen_tab()
        self.create_info_tab()
        self.bind_events()
        
        self.root.after(100, self.process_messages)
        self.root.after(100, self.update_fps_counter)
    
    def create_screen_tab(self):
        status_frame = tk.Frame(self.screen_tab, height=20, bg='#2c3e50')
        status_frame.pack(fill=tk.X)
        status_frame.pack_propagate(False)

        self.status_label = tk.Label(status_frame, text="Не подключено", fg="red", bg='#2c3e50')
        self.status_label.pack(side=tk.LEFT, padx=5)

        self.fps_label = tk.Label(status_frame, text="FPS: 0", fg="white", bg='#2c3e50')
        self.fps_label.pack(side=tk.RIGHT, padx=5)

        self.label = tk.Label(self.screen_tab, bg="black", cursor="crosshair")
        self.label.pack(fill=tk.BOTH, expand=True)
        
        control_frame = tk.Frame(self.screen_tab, height=30, bg='#34495e')
        control_frame.pack(fill=tk.X)
        control_frame.pack_propagate(False)
        
        tk.Button(control_frame, text="Закрыть", command=self.close_client,
                 bg='#e74c3c', fg='white').pack(side=tk.RIGHT, padx=5, pady=2)
    
    def create_info_tab(self):
        # Верхняя панель с кнопкой обновления
        top_frame = tk.Frame(self.info_tab, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.refresh_btn = tk.Button(top_frame, text="🔄 ОБНОВИТЬ ИНФОРМАЦИЮ", 
                                    bg='#3498db', fg='white',
                                    command=self.request_system_info,
                                    state=tk.DISABLED)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.update_time_label = tk.Label(top_frame, text="Последнее обновление: никогда", 
                                         fg='gray', bg='#f0f0f0')
        self.update_time_label.pack(side=tk.RIGHT, padx=5)
        
        # Основная информация
        basic_frame = tk.LabelFrame(self.info_tab, text="Основная информация", font=("Arial", 10, "bold"))
        basic_frame.pack(fill=tk.X, pady=5, padx=5)
        self.basic_info_text = tk.Text(basic_frame, height=5, font=("Consolas", 9))
        self.basic_info_text.pack(fill=tk.X)
        
        # Конфигурация оборудования
        hw_frame = tk.LabelFrame(self.info_tab, text="Конфигурация оборудования", font=("Arial", 10, "bold"))
        hw_frame.pack(fill=tk.X, pady=5, padx=5)
        self.hw_info_text = tk.Text(hw_frame, height=6, font=("Consolas", 9))
        self.hw_info_text.pack(fill=tk.X)
        
        # Метрики производительности
        metrics_frame = tk.LabelFrame(self.info_tab, text="Метрики производительности", font=("Arial", 10, "bold"))
        metrics_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        self.metrics_text = tk.Text(metrics_frame, height=12, font=("Consolas", 9))
        self.metrics_text.pack(fill=tk.BOTH, expand=True)
        
        # События и предупреждения
        events_frame = tk.LabelFrame(self.info_tab, text="События и предупреждения", font=("Arial", 10, "bold"))
        events_frame.pack(fill=tk.X, pady=5, padx=5)
        self.events_text = tk.Text(events_frame, height=3, font=("Consolas", 9))
        self.events_text.pack(fill=tk.X)
    
    def request_system_info(self):
        """Запрашивает информацию о системе у хоста"""
        if self.is_connected and self.loop:
            self.refresh_btn.config(state=tk.DISABLED, text="⏳ ОБНОВЛЕНИЕ...")
            asyncio.run_coroutine_threadsafe(
                self.send_command({"type": "request_system_info", "data": {}}), 
                self.loop
            )
            # Возвращаем кнопку в нормальное состояние через 2 секунды
            self.root.after(2000, lambda: self.refresh_btn.config(state=tk.NORMAL, text="🔄 ОБНОВИТЬ ИНФОРМАЦИЮ"))
    
    def update_system_info_display(self):
        """Обновляет отображение информации о системе"""
        try:
            basic = self.host_info.get("basic", {})
            self.basic_info_text.delete(1.0, tk.END)
            self.basic_info_text.insert(1.0,
                f"Hostname: {basic.get('hostname', 'N/A')}\n"
                f"IP Address: {basic.get('ip_address', 'N/A')}\n"
                f"MAC Address: {basic.get('mac_address', 'N/A')}\n"
                f"OS Version: {basic.get('os_version', 'N/A')}")
            
            hw = self.host_info.get("hardware", {})
            self.hw_info_text.delete(1.0, tk.END)
            self.hw_info_text.insert(1.0,
                f"CPU Model: {hw.get('cpu_model', 'N/A')}\n"
                f"CPU Cores: {hw.get('cpu_cores', 0)} (Physical: {hw.get('cpu_physical_cores', 0)})\n"
                f"RAM Total: {hw.get('ram_total', 0)} GB\n"
                f"Storage Total: {hw.get('storage_total', 0)} GB\n"
                f"GPU Model: {hw.get('gpu_model', 'N/A')}")
            
            metrics = self.host_info.get("metrics", {})
            self.metrics_text.delete(1.0, tk.END)
            self.metrics_text.insert(1.0,
                f"CPU Usage: {metrics.get('cpu_usage', 0)}%\n"
                f"RAM Usage: {metrics.get('ram_usage', 0)}% ({metrics.get('ram_used_gb', 0)} GB / {metrics.get('ram_total_gb', 0)} GB)\n"
                f"Disk Usage: {metrics.get('disk_usage', 0)}% ({metrics.get('disk_used_gb', 0)} GB / {metrics.get('disk_total_gb', 0)} GB)\n"
                f"Timestamp: {metrics.get('timestamp', 'N/A')}")
            
            events = metrics.get('events', [])
            self.events_text.delete(1.0, tk.END)
            if events:
                for event in events:
                    self.events_text.insert(tk.END, f"⚠️ {event.get('description', '')}\n")
            else:
                self.events_text.insert(tk.END, "✅ Нет активных предупреждений")
            
            if self.host_info.get("last_update"):
                self.update_time_label.config(text=f"Последнее обновление: {self.host_info['last_update']}")
            
            # Активируем кнопку обновления
            self.refresh_btn.config(state=tk.NORMAL, text="🔄 ОБНОВИТЬ ИНФОРМАЦИЮ")
        except Exception as e:
            print(f"Ошибка обновления информации: {e}")
    
    def bind_events(self):
        self.label.bind("<Motion>", self.mouse_move)
        self.label.bind("<Button-1>", self.mouse_click)
        self.label.bind("<Button-3>", self.mouse_click)
        self.label.bind("<Button-2>", self.mouse_click)
        self.label.bind("<MouseWheel>", self.mouse_wheel)
        self.root.bind_all("<KeyPress>", self.key_press)
        self.label.bind("<Enter>", self.focus_on_label)
        self.label.focus_set()
    
    def update_status(self, message, message_type="info"):
        def update_ui():
            colors = {"info": "black", "success": "green", "error": "red", "warning": "orange"}
            self.status_label.config(text=message, fg=colors.get(message_type, "black"))
            if "Подключено" in message:
                self.refresh_btn.config(state=tk.NORMAL)
            elif "Отключено" in message:
                self.refresh_btn.config(state=tk.DISABLED)
        self.root.after(0, update_ui)
        if self.status_callback:
            self.status_callback(message, message_type)
    
    def update_fps_counter(self):
        now = time.time()
        if now - self.last_fps_update >= 1.0:
            self.fps_label.config(text=f"FPS: {self.frame_count}")
            self.frame_count = 0
            self.last_fps_update = now
        self.root.after(100, self.update_fps_counter)
    
    def update_image_safe(self, img_tk):
        self.label.config(image=img_tk)
        self.label.image = img_tk
        self.frame_count += 1
    
    def mouse_move(self, event):
        if not self.is_connected:
            return
        if self.host_screen_width and self.host_screen_height:
            scale_x = self.host_screen_width / self.label.winfo_width()
            scale_y = self.host_screen_height / self.label.winfo_height()
            x = int(event.x * scale_x)
            y = int(event.y * scale_y)
            self.command_queue.put({
                "type": "mouse_move", 
                "data": {"action": "mouse_move", "x": x, "y": y}
            })
    
    def mouse_click(self, event):
        if not self.is_connected:
            return
        button = "left" if event.num == 1 else "right" if event.num == 3 else "middle"
        self.command_queue.put({
            "type": "mouse_click", 
            "data": {"action": "mouse_click", "button": button}
        })
    
    def mouse_wheel(self, event):
        if not self.is_connected:
            return
        delta = 1 if event.delta > 0 else -1
        self.command_queue.put({
            "type": "mouse_wheel", 
            "data": {"action": "mouse_wheel", "delta": delta}
        })
    
    def key_press(self, event):
        if not self.is_connected:
            return
        if event.char and event.char != '':
            self.command_queue.put({
                "type": "command", 
                "data": {"action": "text_input", "text": event.char}
            })
    
    def focus_on_label(self, event=None):
        self.label.focus_set()
    
    def close_client(self):
        self.is_connected = False
        if self.ws and self.loop:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        self.root.destroy()
    
    def process_messages(self):
        try:
            while not self.command_queue.empty():
                command = self.command_queue.get_nowait()
                if self.loop and self.is_connected:
                    asyncio.run_coroutine_threadsafe(self.send_command(command), self.loop)
        except:
            pass
        self.root.after(100, self.process_messages)
    
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
                self.is_connected = False
    
    async def client_loop(self):
        reconnect_delay = 2
        while True:
            try:
                self.update_status("Подключение...", "warning")
                
                async with websockets.connect(self.relay_server) as websocket:
                    self.ws = websocket
                    await self.ws.send(json.dumps({
                        "type": "register_client",
                        "data": {"client_id": self.client_id, "host_id": self.host_id},
                        "host_id": self.host_id,
                        "client_id": self.client_id
                    }))
                    
                    self.is_connected = True
                    self.update_status("Подключено", "success")
                    
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
                                win_width = max(self.label.winfo_width(), 1)
                                win_height = max(self.label.winfo_height(), 1)
                                
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
                                    img_tk = ImageTk.PhotoImage(img_resized)
                                    self.root.after(0, self.update_image_safe, img_tk)
                        
                        elif data.get("type") == "system_info":
                            system_data = data.get("data", {})
                            self.host_info = {
                                "basic": system_data.get("basic", {}),
                                "hardware": system_data.get("hardware", {}),
                                "metrics": system_data.get("metrics", {}),
                                "last_update": system_data.get("timestamp", datetime.now().isoformat())
                            }
                            self.root.after(0, self.update_system_info_display)
                            
            except Exception as e:
                self.update_status(f"Ошибка: {e}", "error")
            
            self.is_connected = False
            self.update_status("Отключено", "error")
            await asyncio.sleep(reconnect_delay)
    
    def run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            threading.Thread(target=self.run_asyncio_loop, daemon=True).start()
            self.root.mainloop()
        except Exception as e:
            self.update_status(f"Ошибка: {e}", "error")
    
    def run_asyncio_loop(self):
        try:
            self.loop.run_until_complete(self.client_loop())
        except:
            pass

if __name__ == "__main__":
    app = RemoteAccessClient()
    app.run()