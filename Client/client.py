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

class RemoteAccessClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Удалённый доступ - Настройка")
        self.root.geometry("400x400")
        self.root.configure(bg='#f0f0f0')
        
        # Переменные для настроек
        self.relay_server = tk.StringVar(value="ws://79.174.78.30:9001")
        self.host_id = tk.StringVar(value="PC_HOME")
        self.client_id = tk.StringVar(value="CLIENT")
        self.screen_update_interval = tk.DoubleVar(value=0.033)
        
        # Флаги состояния
        self.is_connected = False
        self.is_running = False
        
        self.create_settings_ui()
        
    def create_settings_ui(self):
        """Создает интерфейс настроек"""
        # Заголовок
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(header_frame, text="🎯 УДАЛЕННЫЙ ДОСТУП", 
                              font=("Arial", 16, "bold"), fg='white', bg='#2c3e50')
        title_label.pack(pady=15)
        
        # Основная область настроек
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Настройки соединения
        settings_frame = tk.LabelFrame(main_frame, text="Настройки соединения", 
                                     font=("Arial", 10, "bold"), bg='#f0f0f0', padx=10, pady=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Сервер ретрансляции
        tk.Label(settings_frame, text="Сервер ретрансляции:", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=0, column=0, sticky='w', pady=2)
        server_entry = tk.Entry(settings_frame, textvariable=self.relay_server, 
                               font=("Arial", 9), width=30)
        server_entry.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        # ID хоста
        tk.Label(settings_frame, text="ID хоста:", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=1, column=0, sticky='w', pady=2)
        host_entry = tk.Entry(settings_frame, textvariable=self.host_id, 
                             font=("Arial", 9), width=30)
        host_entry.grid(row=1, column=1, padx=5, pady=2, sticky='ew')
        
        # ID клиента
        tk.Label(settings_frame, text="ID клиента:", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=2, column=0, sticky='w', pady=2)
        client_entry = tk.Entry(settings_frame, textvariable=self.client_id, 
                               font=("Arial", 9), width=30)
        client_entry.grid(row=2, column=1, padx=5, pady=2, sticky='ew')
        
        # Настройки производительности
        perf_frame = tk.LabelFrame(main_frame, text="Настройки производительности", 
                                 font=("Arial", 10, "bold"), bg='#f0f0f0', padx=10, pady=10)
        perf_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Интервал обновления экрана
        tk.Label(perf_frame, text="Интервал обновления (сек):", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=0, column=0, sticky='w', pady=2)
        
        interval_frame = tk.Frame(perf_frame, bg='#f0f0f0')
        interval_frame.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        interval_scale = tk.Scale(interval_frame, from_=0.01, to=0.1, 
                                 resolution=0.01, orient=tk.HORIZONTAL,
                                 variable=self.screen_update_interval,
                                 length=200, showvalue=True, bg='#f0f0f0')
        interval_scale.pack(fill=tk.X)
        
        # Кнопки управления
        button_frame = tk.Frame(main_frame, bg='#f0f0f0')
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = tk.Button(button_frame, text="🟢 УДАЛЕННЫЙ ДОСТУП", 
                                 font=("Arial", 12, "bold"), bg='#27ae60', fg='white',
                                 command=self.start_client, width=20, height=2)
        self.start_btn.pack(pady=5)
        
        self.stop_btn = tk.Button(button_frame, text="🔴 ОСТАНОВИТЬ", 
                                font=("Arial", 10, "bold"), bg='#e74c3c', fg='white',
                                command=self.stop_client, width=15, height=1, state=tk.DISABLED)
        self.stop_btn.pack(pady=2)
        
        # Статус
        self.status_label = tk.Label(main_frame, text="🔴 Клиент не запущен", 
                                   font=("Arial", 10), bg='#f0f0f0', fg='red')
        self.status_label.pack(pady=5)
        
        # Настройка весов колонок для растягивания
        settings_frame.columnconfigure(1, weight=1)
        perf_frame.columnconfigure(1, weight=1)
        
    def start_client(self):
        """Запускает клиент удаленного доступа"""
        try:
            # Проверяем настройки
            if not self.relay_server.get().startswith('ws://'):
                messagebox.showerror("Ошибка", "Сервер должен начинаться с ws://")
                return
                
            if not self.host_id.get():
                messagebox.showerror("Ошибка", "Введите ID хоста")
                return
                
            # Обновляем UI
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_label.config(text="🟡 Запуск клиента...", fg='orange')
            
            # Запускаем клиент в отдельном потоке
            self.is_running = True
            client_thread = threading.Thread(target=self.run_client, daemon=True)
            client_thread.start()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка запуска: {e}")
            self.stop_client()
    
    def stop_client(self):
        """Останавливает клиент"""
        self.is_running = False
        self.is_connected = False
        
        # Обновляем UI
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="🔴 Клиент остановлен", fg='red')
    
    def run_client(self):
        """Запускает основной клиент"""
        try:
            # Импортируем и запускаем клиент с текущими настройками
            client = RemoteClient(
                relay_server=self.relay_server.get(),
                host_id=self.host_id.get(),
                client_id=self.client_id.get(),
                update_interval=self.screen_update_interval.get(),
                status_callback=self.update_status
            )
            client.run()
        except Exception as e:
            self.update_status(f"❌ Ошибка: {e}", "error")
    
    def update_status(self, message, message_type="info"):
        """Обновляет статус в UI"""
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
        """Запускает приложение"""
        self.root.mainloop()

class RemoteClient:
    def __init__(self, relay_server, host_id, client_id, update_interval, status_callback):
        self.relay_server = relay_server
        self.host_id = host_id
        self.client_id = client_id
        self.update_interval = update_interval
        self.status_callback = status_callback
        
        # Глобальные переменные
        self.ws = None
        self.loop = None
        self.root = None
        self.host_screen_width = None
        self.host_screen_height = None
        self.command_queue = queue.Queue()
        self.is_connected = False
        self.frame_count = 0
        self.last_fps_update = 0
        
        # Создаем UI
        self.create_ui()
    
    def create_ui(self):
        """Создает UI клиента"""
        self.root = tk.Toplevel()
        self.root.title(f"Удалённый доступ - {self.host_id}")
        self.root.geometry("800x600")
        
        # Панель статуса
        status_frame = tk.Frame(self.root, height=20)
        status_frame.pack(fill=tk.X, padx=5, pady=2)
        status_frame.pack_propagate(False)

        self.status_label = tk.Label(status_frame, text="🔴 Не подключено", fg="red")
        self.status_label.pack(side=tk.LEFT)

        self.fps_label = tk.Label(status_frame, text="FPS: 0", fg="gray")
        self.fps_label.pack(side=tk.RIGHT)

        self.label = tk.Label(self.root, bg="black", cursor="crosshair")
        self.label.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки управления
        control_frame = tk.Frame(self.root, height=30)
        control_frame.pack(fill=tk.X, padx=5, pady=2)
        control_frame.pack_propagate(False)
        
        tk.Button(control_frame, text="🔄 Обновить", command=self.manual_refresh).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="⚙️ Настройки", command=self.show_settings).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="❌ Закрыть", command=self.close_client).pack(side=tk.RIGHT, padx=5)
        
        # Привязка событий
        self.bind_events()
        
        # Запускаем обработку сообщений
        self.root.after(100, self.process_messages)
        self.root.after(100, self.update_fps_counter)
    
    def bind_events(self):
        """Привязывает события мыши и клавиатуры"""
        self.label.bind("<Motion>", self.mouse_move)
        self.label.bind("<Button-1>", self.mouse_click)
        self.label.bind("<Button-3>", self.mouse_click)
        self.label.bind("<Button-2>", self.mouse_click)
        self.label.bind("<MouseWheel>", self.mouse_wheel)
        
        self.root.bind_all("<KeyPress>", self.key_press)
        
        # Комбинации клавиш
        self.root.bind_all("<Control-c>", lambda e: self.key_combination('ctrl+c'))
        self.root.bind_all("<Control-v>", lambda e: self.key_combination('ctrl+v'))
        self.root.bind_all("<Control-x>", lambda e: self.key_combination('ctrl+x'))
        self.root.bind_all("<Control-a>", lambda e: self.key_combination('ctrl+a'))
        
        self.label.bind("<Enter>", self.focus_on_label)
        self.label.focus_set()
    
    def update_status(self, message, message_type="info"):
        """Обновляет статус"""
        def update_ui():
            colors = {"info": "black", "success": "green", "error": "red", "warning": "orange"}
            color = colors.get(message_type, "black")
            self.status_label.config(text=message, fg=color)
            
        self.root.after(0, update_ui)
        # Также отправляем в основной UI
        if self.status_callback:
            self.status_callback(message, message_type)
    
    def update_fps_counter(self):
        """Обновляет счетчик FPS"""
        now = time.time()
        if now - self.last_fps_update >= 1.0:
            self.fps_label.config(text=f"FPS: {self.frame_count}")
            self.frame_count = 0
            self.last_fps_update = now
        self.root.after(100, self.update_fps_counter)
    
    def update_image_safe(self, img_tk):
        """Безопасно обновляет изображение"""
        self.label.config(image=img_tk)
        self.label.image = img_tk
        self.frame_count += 1
    
    # Обработчики событий (аналогичные вашим)
    def mouse_move(self, event):
        if not self.is_connected:
            return
        
        if self.host_screen_width and self.host_screen_height and self.label.winfo_width() > 10 and self.label.winfo_height() > 10:
            scale_x = self.host_screen_width / self.label.winfo_width()
            scale_y = self.host_screen_height / self.label.winfo_height()
            x = max(0, min(int(event.x * scale_x), self.host_screen_width - 1))
            y = max(0, min(int(event.y * scale_y), self.host_screen_height - 1))
            
            self.command_queue.put({
                "type": "mouse_move", 
                "data": {"action": "mouse_move", "x": x, "y": y}
            })
    
    def mouse_click(self, event):
        if not self.is_connected:
            return
            
        button = "left"
        if event.num == 3:
            button = "right"
        elif event.num == 2:
            button = "middle"
        
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
            
        # Игнорируем специальные клавиши
        special_keys = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12',
                       'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Shift_L', 'Shift_R', 
                       'Super_L', 'Super_R', 'Caps_Lock', 'Num_Lock', 'Scroll_Lock']
        
        if event.keysym in special_keys:
            return
        
        # Обрабатываем печатные символы
        if hasattr(event, 'char') and event.char and event.char != '':
            print(f"Нажат символ: '{event.char}' (keysym: {event.keysym})")
            self.command_queue.put({
                "type": "command", 
                "data": {"action": "text_input", "text": event.char}
            })
        else:
            # Обрабатываем остальные клавиши
            key_mapping = {
                'Return': 'enter', 'BackSpace': 'backspace', 'Delete': 'delete',
                'Tab': 'tab', 'Escape': 'esc', 'Left': 'left', 'Right': 'right', 
                'Up': 'up', 'Down': 'down', 'Home': 'home', 'End': 'end',
                'Page_Up': 'pageup', 'Page_Down': 'pagedown'
            }
            
            if event.keysym in key_mapping:
                self.command_queue.put({
                    "type": "key_press", 
                    "data": {"action": "key_press", "key": key_mapping[event.keysym]}
                })
    
    def key_combination(self, combination):
        """Обработка комбинаций клавиш"""
        if not self.is_connected:
            return
            
        self.command_queue.put({
            "type": "command",
            "data": {"action": "key_combination", "keys": combination}
        })
    
    def focus_on_label(self, event=None):
        self.label.focus_set()
    
    def manual_refresh(self):
        """Ручное обновление экрана"""
        if self.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(self.send_command({'command': 'get_screen'}), self.loop)
    
    def show_settings(self):
        """Показывает окно настроек"""
        messagebox.showinfo("Настройки", 
                           f"Сервер: {self.relay_server}\n"
                           f"Хост: {self.host_id}\n"
                           f"Клиент: {self.client_id}\n"
                           f"Интервал: {self.update_interval} сек")
    
    def close_client(self):
        """Закрывает клиент"""
        self.is_connected = False
        if self.ws and self.loop:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        self.root.destroy()
    
    def process_messages(self):
        """Обрабатывает сообщения из очереди"""
        try:
            while not self.command_queue.empty():
                command = self.command_queue.get_nowait()
                if self.loop and self.is_connected:
                    asyncio.run_coroutine_threadsafe(self.send_command(command), self.loop)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Ошибка обработки очереди: {e}")
        
        self.root.after(100, self.process_messages)
    
    async def send_command(self, command):
        """Отправляет команду на сервер"""
        if self.ws and self.is_connected:
            try:
                message = {
                    "type": command["type"], 
                    "data": command.get("data"), 
                    "host_id": self.host_id,
                    "client_id": self.client_id
                }
                await self.ws.send(json.dumps(message))
            except Exception as e:
                print(f"Ошибка отправки команды: {e}")
                self.is_connected = False
    
    async def client_loop(self):
        """Основной цикл клиента"""
        reconnect_delay = 2
        
        while True:
            try:
                self.update_status("🔄 Подключение...", "warning")
                print(f"🔄 Подключение к {self.relay_server}...")
                
                async with websockets.connect(
                    self.relay_server,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    self.ws = websocket
                    await self.ws.send(json.dumps({
                        "type": "register_client",
                        "data": {"client_id": self.client_id, "host_id": self.host_id}
                    }))
                    
                    print("✅ Подключено к хосту")
                    self.is_connected = True
                    self.update_status("🟢 Подключено", "success")
                    
                    queue_handler = asyncio.create_task(self.process_command_queue())
                    last_update = 0
                    
                    try:
                        while True:
                            try:
                                msg = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                                data = json.loads(msg)
                                
                                if data.get("type") == "screenshot":
                                    now = time.time()
                                    if now - last_update >= self.update_interval:
                                        last_update = now
                                        
                                        img_data = base64.b64decode(data["data"])
                                        img = Image.open(BytesIO(img_data))
                                        
                                        new_width, new_height = img.size
                                        if (self.host_screen_width, self.host_screen_height) != (new_width, new_height):
                                            self.host_screen_width, self.host_screen_height = new_width, new_height
                                            print(f"📐 Разрешение экрана: {new_width}x{new_height}")

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
                                    
                            except asyncio.TimeoutError:
                                continue
                            except websockets.exceptions.ConnectionClosed:
                                print("❌ Соединение разорвано")
                                break
                                
                    finally:
                        queue_handler.cancel()
                        try:
                            await queue_handler
                        except asyncio.CancelledError:
                            pass
                            
            except ConnectionRefusedError:
                print(f"❌ Сервер недоступен. Переподключение через {reconnect_delay}с...")
                self.update_status("❌ Сервер недоступен", "error")
            except Exception as e:
                print(f"❌ Ошибка: {e}. Переподключение через {reconnect_delay}с...")
                self.update_status(f"❌ Ошибка: {e}", "error")
            
            self.is_connected = False
            self.update_status("🔴 Отключено", "error")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, 30)
    
    async def process_command_queue(self):
        """Обрабатывает очередь команд"""
        while True:
            try:
                if not self.command_queue.empty():
                    command = self.command_queue.get_nowait()
                    await self.send_command(command)
                await asyncio.sleep(0.001)
            except Exception as e:
                print(f"Ошибка обработки очереди: {e}")
    
    def run(self):
        """Запускает клиент"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Запускаем asyncio в отдельном потоке
            threading.Thread(target=self.run_asyncio_loop, daemon=True).start()
            
            # Запускаем UI
            self.root.mainloop()
            
        except Exception as e:
            self.update_status(f"❌ Ошибка запуска: {e}", "error")
    
    def run_asyncio_loop(self):
        """Запускает asyncio loop"""
        try:
            self.loop.run_until_complete(self.client_loop())
        except Exception as e:
            print(f"❌ Ошибка в asyncio loop: {e}")

if __name__ == "__main__":
    app = RemoteAccessClient()
    app.run()