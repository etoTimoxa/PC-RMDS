import asyncio
import websockets
import json
import logging
import sys
import mss
from io import BytesIO
from PIL import Image
import base64
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Перенаправляем stdout и stderr чтобы избежать ошибок при --noconsole
if getattr(sys, 'frozen', False):
    # Если приложение собрано в exe
    sys.stdout = open('stdout.log', 'w', encoding='utf-8')
    sys.stderr = open('stderr.log', 'w', encoding='utf-8')

# Настраиваем логирование в файл
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('host_errors.log', encoding='utf-8'),
    ]
)

class RemoteAccessHost:
    def __init__(self):
        # Перенаправляем стандартные потоки при запуске
        self.redirect_std_streams()
        
        self.root = tk.Tk()
        self.root.title("Удалённый доступ - Хост")
        self.root.geometry("700x600")
        self.root.configure(bg='#f0f0f0')
        
        # Переменные для настроек
        self.relay_server = tk.StringVar(value="ws://79.174.78.30:9001")
        self.host_id = tk.StringVar(value="PC_HOME")
        self.screenshot_interval = tk.DoubleVar(value=0.1)
        
        # Флаги состояния
        self.is_running = False
        self.is_connected = False
        self.connected_clients = 0
        self.tray_icon = None
        
        # Инициализация контроллеров
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
        # Получаем разрешение экрана
        try:
            import pyautogui
            self.screen_width, self.screen_height = pyautogui.size()
        except:
            self.screen_width, self.screen_height = 1920, 1080
        
        # Таблица преобразования клавиш
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
            'caps_lock': Key.caps_lock, 'print_screen': Key.print_screen,
            'scroll_lock': Key.scroll_lock, 'pause': Key.pause,
            'insert': Key.insert, 'menu': Key.menu,
        }
        
        # WebSocket переменные
        self.ws = None
        self.loop = None
        
        self.create_ui()
        
        # Запрещаем закрытие окна крестиком
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
    
    def redirect_std_streams(self):
        """Перенаправляет stdout и stderr для работы с --noconsole"""
        try:
            # Создаем пустые файловые объекты
            class NullWriter:
                def write(self, text):
                    pass
                def flush(self):
                    pass
                def isatty(self):
                    return False
            
            null_writer = NullWriter()
            
            # Перенаправляем стандартные потоки
            sys.stdout = null_writer
            sys.stderr = null_writer
            
            # Также перенаправляем для asyncio
            if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
                # Для Windows
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
        except Exception as e:
            # В случае ошибки просто игнорируем
            pass
        
    def create_ui(self):
        """Создает интерфейс хоста"""
        # Заголовок
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(header_frame, text="🎯 ХОСТ УДАЛЕННОГО ДОСТУПА", 
                              font=("Arial", 16, "bold"), fg='white', bg='#2c3e50')
        title_label.pack(pady=15)
        
        # Основная область
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Левая панель - настройки и управление
        left_frame = tk.Frame(main_frame, bg='#f0f0f0')
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Правая панель - лог
        right_frame = tk.Frame(main_frame, bg='#f0f0f0')
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # === ЛЕВАЯ ПАНЕЛЬ ===
        
        # Статус хоста
        status_frame = tk.LabelFrame(left_frame, text="Статус хоста", font=("Arial", 10, "bold"), 
                                   bg='#f0f0f0', padx=10, pady=10)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_label = tk.Label(status_frame, text="🔴 ХОСТ ОСТАНОВЛЕН", 
                                   font=("Arial", 12, "bold"), fg='red', bg='#f0f0f0')
        self.status_label.pack(pady=5)
        
        self.clients_label = tk.Label(status_frame, text="Подключенных клиентов: 0", 
                                    font=("Arial", 10), bg='#f0f0f0')
        self.clients_label.pack(pady=2)
        
        # Настройки соединения
        settings_frame = tk.LabelFrame(left_frame, text="Настройки соединения", 
                                     font=("Arial", 10, "bold"), bg='#f0f0f0', padx=10, pady=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Сервер ретрансляции
        tk.Label(settings_frame, text="Сервер ретрансляции:", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=0, column=0, sticky='w', pady=2)
        server_entry = tk.Entry(settings_frame, textvariable=self.relay_server, 
                               font=("Arial", 9), width=25)
        server_entry.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        # ID хоста
        tk.Label(settings_frame, text="ID хоста:", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=1, column=0, sticky='w', pady=2)
        host_entry = tk.Entry(settings_frame, textvariable=self.host_id, 
                             font=("Arial", 9), width=25)
        host_entry.grid(row=1, column=1, padx=5, pady=2, sticky='ew')
        
        # Интервал скриншотов
        tk.Label(settings_frame, text="Интервал скриншотов:", 
                bg='#f0f0f0', font=("Arial", 9)).grid(row=2, column=0, sticky='w', pady=2)
        
        interval_frame = tk.Frame(settings_frame, bg='#f0f0f0')
        interval_frame.grid(row=2, column=1, padx=5, pady=2, sticky='ew')
        
        interval_scale = tk.Scale(interval_frame, from_=0.05, to=0.5, 
                                 resolution=0.05, orient=tk.HORIZONTAL,
                                 variable=self.screenshot_interval,
                                 length=150, showvalue=True, bg='#f0f0f0')
        interval_scale.pack(fill=tk.X)
        
        # Управление
        control_frame = tk.LabelFrame(left_frame, text="Управление", font=("Arial", 10, "bold"),
                                    bg='#f0f0f0', padx=10, pady=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.start_btn = tk.Button(control_frame, text="🟢 ЗАПУСТИТЬ ХОСТ", 
                                 font=("Arial", 10, "bold"), bg='#27ae60', fg='white',
                                 command=self.start_host, width=18, height=2)
        self.start_btn.pack(pady=5)
        
        self.stop_btn = tk.Button(control_frame, text="🔴 ОСТАНОВИТЬ ХОСТ", 
                                font=("Arial", 10, "bold"), bg='#e74c3c', fg='white',
                                command=self.stop_host, width=18, height=2, state=tk.DISABLED)
        self.stop_btn.pack(pady=5)
        
        # === ПРАВАЯ ПАНЕЛЬ - ЛОГ ===
        
        log_frame = tk.LabelFrame(right_frame, text="Журнал событий", font=("Arial", 10, "bold"),
                                bg='#f0f0f0', padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=50, height=20,
                                                font=("Consolas", 9), bg='#2c3e50', fg='#ecf0f1')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки управления логом
        log_buttons_frame = tk.Frame(log_frame, bg='#f0f0f0')
        log_buttons_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(log_buttons_frame, text="🧹 Очистить лог", command=self.clear_log,
                 font=("Arial", 8), bg='#7f8c8d', fg='white').pack(side=tk.LEFT)
        
        tk.Button(log_buttons_frame, text="💾 Сохранить лог", command=self.save_log,
                 font=("Arial", 8), bg='#3498db', fg='white').pack(side=tk.LEFT, padx=5)
        
        # Нижняя панель
        bottom_frame = tk.Frame(self.root, bg='#34495e', height=30)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        bottom_frame.pack_propagate(False)
        
        tk.Button(bottom_frame, text="📌 Свернуть в трей", command=self.minimize_to_tray,
                 font=("Arial", 8), bg='#34495e', fg='white', bd=0).pack(side=tk.RIGHT, padx=10, pady=5)
        
        tk.Button(bottom_frame, text="❌ Выход", command=self.quit_application,
                 font=("Arial", 8), bg='#e74c3c', fg='white').pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Настройка весов колонок
        settings_frame.columnconfigure(1, weight=1)
        
    def minimize_to_tray(self):
        """Сворачивает окно в трей"""
        if HAS_PYSTRAY:
            self.root.withdraw()
            self.create_tray_icon()
        else:
            self.log_message("⚠️ Библиотека pystray не установлена. Окно останется открытым.", "warning")
    
    def create_tray_icon(self):
        """Создает иконку в трее"""
        if not HAS_PYSTRAY:
            return
            
        def create_image():
            # Создаем изображение для иконки в трее
            image = Image.new('RGB', (64, 64), color='green' if self.is_running else 'red')
            dc = ImageDraw.Draw(image)
            # Рисуем простой компьютер
            dc.rectangle([16, 16, 48, 40], outline='white', width=3)
            dc.rectangle([24, 40, 40, 48], fill='white')
            return image

        def show_window(icon, item):
            """Показывает окно приложения"""
            icon.stop()
            self.root.deiconify()
            self.root.after(0, self.root.lift)

        def quit_app(icon, item):
            """Выход из приложения"""
            icon.stop()
            self.quit_application()

        # Создаем меню для иконки в трее
        menu = pystray.Menu(
            Item('📱 Развернуть окно', show_window),
            Item('🟢 Запустить хост', self.start_host) if not self.is_running else 
            Item('🔴 Остановить хост', self.stop_host),
            Item('❌ Выход', quit_app)
        )
        
        self.tray_icon = pystray.Icon(
            "remote_host",
            create_image(),
            f"Хост удаленного доступа - {self.host_id.get()}",
            menu=menu
        )
        
        # Запускаем иконку в трее
        self.tray_icon.run()
    
    def update_tray_icon(self):
        """Обновляет иконку в трее"""
        if self.tray_icon:
            # Обновляем иконку (зеленая если запущено, красная если остановлено)
            def create_updated_image():
                image = Image.new('RGB', (64, 64), color='green' if self.is_running else 'red')
                dc = ImageDraw.Draw(image)
                dc.rectangle([16, 16, 48, 40], outline='white', width=3)
                dc.rectangle([24, 40, 40, 48], fill='white')
                return image
            
            self.tray_icon.icon = create_updated_image()
            self.tray_icon.title = f"Хост удаленного доступа - {self.host_id.get()} ({'Активен' if self.is_running else 'Остановлен'})"
    
    def log_message(self, message, message_type="info"):
        """Добавляет сообщение в лог"""
        try:
            timestamp = time.strftime("%H:%M:%S")
            
            colors = {
                "info": "#3498db",
                "success": "#27ae60", 
                "warning": "#f39c12",
                "error": "#e74c12",
                "client": "#9b59b6"
            }
            
            color = colors.get(message_type, "#3498db")
            formatted_message = f"[{timestamp}] {message}\n"
            
            self.log_text.insert(tk.END, formatted_message)
            start_index = self.log_text.index("end-2l")
            end_index = self.log_text.index("end-1l")
            
            self.log_text.tag_add(message_type, start_index, end_index)
            self.log_text.tag_config(message_type, foreground=color)
            self.log_text.see(tk.END)
        except Exception:
            # Игнорируем ошибки логирования в UI
            pass
    
    def clear_log(self):
        """Очищает лог"""
        try:
            self.log_text.delete(1.0, tk.END)
        except Exception:
            pass
    
    def save_log(self):
        """Сохраняет лог в файл"""
        try:
            with open("host_log.txt", "w", encoding="utf-8") as f:
                log_content = self.log_text.get(1.0, tk.END)
                f.write(log_content)
            self.log_message("✅ Лог сохранен в host_log.txt", "success")
        except Exception as e:
            self.log_message(f"❌ Ошибка сохранения лога: {e}", "error")
    
    def update_ui_status(self):
        """Обновляет статус в интерфейсе"""
        try:
            if self.is_running and self.is_connected:
                self.status_label.config(text="🟢 ХОСТ АКТИВЕН", fg='#27ae60')
                self.clients_label.config(text=f"Подключенных клиентов: {self.connected_clients}")
                self.start_btn.config(state=tk.DISABLED)
                self.stop_btn.config(state=tk.NORMAL)
            elif self.is_running and not self.is_connected:
                self.status_label.config(text="🟡 ПОДКЛЮЧЕНИЕ...", fg='#f39c12')
                self.start_btn.config(state=tk.DISABLED)
                self.stop_btn.config(state=tk.NORMAL)
            else:
                self.status_label.config(text="🔴 ХОСТ ОСТАНОВЛЕН", fg='#e74c3c')
                self.clients_label.config(text="Подключенных клиентов: 0")
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
            
            # Обновляем иконку в трее
            self.update_tray_icon()
        except Exception:
            # Игнорируем ошибки обновления UI
            pass
    
    def test_pynput(self):
        """Тестирует работу pynput"""
        try:
            current_pos = self.mouse.position
            self.log_message(f"✅ Pynput работает. Позиция мыши: {current_pos}", "success")
            return True
        except Exception as e:
            self.log_message(f"❌ Ошибка pynput: {e}", "error")
            return False
    
    def test_screenshot(self):
        """Тестирует захват скриншота"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                self.log_message(f"✅ Скриншот захвачен: {sct_img.width}x{sct_img.height}", "success")
            return True
        except Exception as e:
            self.log_message(f"❌ Ошибка скриншота: {e}", "error")
            return False
    
    def start_host(self):
        """Запускает хост"""
        try:
            # Проверяем настройки
            if not self.relay_server.get().startswith('ws://'):
                messagebox.showerror("Ошибка", "Сервер должен начинаться с ws://")
                return
                
            if not self.host_id.get():
                messagebox.showerror("Ошибка", "Введите ID хоста")
                return
            
            # Тестируем pynput
            if not self.test_pynput():
                messagebox.showerror("Ошибка", "Pynput не работает! Проверьте установку и права.")
                return
            
            # Обновляем UI
            self.is_running = True
            self.update_ui_status()
            self.log_message("🚀 Запуск хоста...", "info")
            
            # Запускаем хост в отдельном потоке
            host_thread = threading.Thread(target=self.run_host, daemon=True)
            host_thread.start()
            
        except Exception as e:
            try:
                messagebox.showerror("Ошибка", f"Ошибка запуска: {e}")
            except:
                pass
            self.stop_host()
    
    def stop_host(self):
        """Останавливает хост"""
        self.is_running = False
        self.is_connected = False
        self.connected_clients = 0
        
        if self.loop and self.ws:
            try:
                asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
            except:
                pass
        
        self.update_ui_status()
        self.log_message("🔴 Хост остановлен", "warning")
    
    def run_host(self):
        """Запускает основной цикл хоста"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.host_main())
        except Exception as e:
            self.log_message(f"❌ Ошибка в основном цикле: {e}", "error")
            self.stop_host()
    
    async def host_main(self):
        """Основная асинхронная функция хоста"""
        reconnect_delay = 2
        max_reconnect_delay = 30
        
        while self.is_running:
            try:
                self.log_message(f"🔗 Подключение к серверу {self.relay_server.get()}...", "info")
                
                async with websockets.connect(self.relay_server.get(), ping_interval=20, ping_timeout=10) as ws:
                    self.ws = ws
                    if await self.send_message(ws, "register_host", {"host_id": self.host_id.get()}):
                        self.is_connected = True
                        self.update_ui_status()
                        self.log_message(f"✅ Зарегистрирован на сервере как {self.host_id.get()}", "success")
                        reconnect_delay = 2
                        
                        send_task = asyncio.create_task(self.send_loop(ws))
                        receive_task = asyncio.create_task(self.receive_commands(ws))
                        
                        done, pending = await asyncio.wait(
                            [send_task, receive_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        for task in pending:
                            task.cancel()
                        
                        for task in pending:
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        
                        self.log_message("🔌 Соединение разорвано", "warning")
                        
            except ConnectionRefusedError:
                self.log_message(f"❌ Сервер недоступен, переподключение через {reconnect_delay} сек...", "error")
            except websockets.exceptions.WebSocketException as e:
                self.log_message(f"❌ Ошибка соединения: {e}, переподключение через {reconnect_delay} сек...", "error")
            except Exception as e:
                self.log_message(f"❌ Неожиданная ошибка: {e}, переподключение через {reconnect_delay} сек...", "error")
            
            self.is_connected = False
            self.update_ui_status()
            
            if self.is_running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
    
    async def send_message(self, ws, msg_type, data=None):
        """Отправляет сообщение"""
        try:
            message = {"type": msg_type, "data": data, "host_id": self.host_id.get()}
            await ws.send(json.dumps(message))
            return True
        except websockets.exceptions.ConnectionClosed:
            return False
        except Exception as e:
            self.log_message(f"❌ Ошибка отправки: {e}", "error")
            return False
    
    async def send_screenshot(self, ws):
        """Отправляет скриншот"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=50)
                img_b64 = base64.b64encode(buffer.getvalue()).decode()
                return await self.send_message(ws, "screenshot", img_b64)
        except Exception as e:
            self.log_message(f"❌ Ошибка скриншота: {e}", "error")
            return False
    
    async def send_loop(self, ws):
        """Цикл отправки скриншотов"""
        while self.is_running and self.is_connected:
            try:
                success = await self.send_screenshot(ws)
                if not success:
                    break
                await asyncio.sleep(self.screenshot_interval.get())
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                self.log_message(f"❌ Ошибка в send_loop: {e}", "error")
                await asyncio.sleep(1)
    
    async def handle_command(self, command):
        """Обрабатывает команды от клиента"""
        try:
            action = command.get("action")

            if action == "mouse_move":
                x = command.get("x")
                y = command.get("y")
                if x is not None and y is not None:
                    x = max(0, min(x, self.screen_width - 1))
                    y = max(0, min(y, self.screen_height - 1))
                    self.mouse.position = (x, y)

            elif action == "mouse_click":
                button_name = command.get("button", "left")
                button = Button.left if button_name == "left" else Button.right
                self.mouse.click(button)
                self.log_message(f"🖱️ Клик мыши: {button_name}", "info")

            elif action == "mouse_wheel":
                delta = command.get("delta", 0)
                self.mouse.scroll(0, delta)
                self.log_message(f"🖱️ Прокрутка: {delta}", "info")

            elif action == "key_press":
                key = command.get("key")
                if key:
                    normalized_key = key.lower()
                    if normalized_key in self.KEY_MAPPING:
                        self.keyboard.press(self.KEY_MAPPING[normalized_key])
                        self.keyboard.release(self.KEY_MAPPING[normalized_key])
                    else:
                        self.keyboard.press(normalized_key)
                        self.keyboard.release(normalized_key)
                    self.log_message(f"⌨️ Нажата клавиша: {key}", "info")

            elif action == "key_combination":
                keys = command.get("keys")
                if keys:
                    key_list = [k.strip().lower() for k in keys.split('+')]
                    
                    for key in key_list[:-1]:
                        if key in self.KEY_MAPPING:
                            self.keyboard.press(self.KEY_MAPPING[key])
                        else:
                            self.keyboard.press(key)
                    
                    main_key = key_list[-1]
                    if main_key in self.KEY_MAPPING:
                        self.keyboard.press(self.KEY_MAPPING[main_key])
                        self.keyboard.release(self.KEY_MAPPING[main_key])
                    else:
                        self.keyboard.press(main_key)
                        self.keyboard.release(main_key)
                    
                    for key in key_list[:-1]:
                        if key in self.KEY_MAPPING:
                            self.keyboard.release(self.KEY_MAPPING[key])
                        else:
                            self.keyboard.release(key)
                    
                    self.log_message(f"⌨️ Комбинация: {keys}", "info")

            elif action == "text_input":
                text = command.get("text", "")
                if text:
                    self.keyboard.type(text)
                    self.log_message(f"⌨️ Введен текст: '{text}'", "info")

            elif action == "run":
                cmd = command.get("cmd")
                if not cmd:
                    return {"error": "Не указана команда для выполнения"}
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
                return {
                    "output": result.stdout.strip(), 
                    "error": result.stderr.strip(),
                    "returncode": result.returncode
                }

            return {"status": "ok"}

        except Exception as e:
            self.log_message(f"❌ Ошибка выполнения команды: {e}", "error")
            return {"error": str(e)}
    
    async def receive_commands(self, ws):
        """Получает команды от клиентов"""
        try:
            async for msg in ws:
                try:
                    data = json.loads(msg)
                    cmd_type = data.get("type")
                    command = data.get("data", {})

                    if cmd_type == "register_client":
                        self.connected_clients += 1
                        self.update_ui_status()
                        client_id = data.get("client_id", "unknown")
                        self.log_message(f"🔗 Подключен клиент: {client_id}", "client")
                    
                    elif cmd_type in ["mouse_move", "mouse_click", "key_press", "mouse_wheel", "command"]:
                        result = await self.handle_command(command)
                        if cmd_type == "command":
                            await self.send_message(ws, "command_result", result)
                            
                except json.JSONDecodeError:
                    self.log_message("❌ Ошибка декодирования JSON", "error")
                except Exception as e:
                    self.log_message(f"❌ Ошибка обработки команды: {e}", "error")
                    
        except websockets.exceptions.ConnectionClosed:
            self.log_message("🔌 Соединение для команд закрыто", "warning")
        except Exception as e:
            self.log_message(f"❌ Ошибка в receive_commands: {e}", "error")
    
    def quit_application(self):
        """Выход из приложения"""
        self.stop_host()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except:
                pass
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
    
    def run(self):
        """Запускает приложение"""
        try:
            self.log_message("🚀 Приложение хоста запущено", "success")
            self.log_message(f"💻 Разрешение экрана: {self.screen_width}x{self.screen_height}", "info")
            self.root.mainloop()
        except KeyboardInterrupt:
            self.log_message("⏹️ Остановлено пользователем", "info")
        except Exception as e:
            self.log_message(f"❌ Критическая ошибка: {e}", "error")

if __name__ == "__main__":
    app = RemoteAccessHost()
    app.run()