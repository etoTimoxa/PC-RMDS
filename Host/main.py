import sys
import os
from pathlib import Path
import threading
import asyncio
import multiprocessing
from datetime import datetime

os.environ['QT_API'] = 'pyqt5'

# Указываем путь к плагинам PyQt5
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    # В виртуальном окружении
    import PyQt5
    qt_plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins')
else:
    # В глобальном окружении
    qt_plugin_path = os.path.join(sys.prefix, 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins')

os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qt_plugin_path, 'platforms')

from qtpy.QtWidgets import QApplication, QMessageBox
from qtpy.QtCore import QSettings, QTimer

from admin.auth_dialog import AuthDialog
from agent.remote_agent import RemoteAgentWindow
from admin.admin_panel import AdminPanelWindow
from utils.dependencies import DependencyChecker
from utils.platform_utils import ensure_dirs, get_platform_name, get_data_dir
from core.api_client import APIClient
from core.hardware_id import HardwareIDGenerator


class AgentBackgroundService:
    """Сервис для запуска агента в фоновом режиме (для администратора)"""
    
    def __init__(self, computer_data: dict):
        self.computer_data = computer_data
        self.agent_thread = None
        self.running = False
        self.agent_instance = None
        
    def start(self):
        """Запускает агента в отдельном потоке"""
        if self.running:
            print("[BACKGROUND] Агент уже запущен")
            return
        
        self.running = True
        self.agent_thread = threading.Thread(target=self._run_agent, daemon=True)
        self.agent_thread.start()
        print(f"[BACKGROUND] Агент запущен в фоновом режиме для админа {self.computer_data.get('login')}")
    
    def _run_agent(self):
        """Запускает полноценного агента в этом потоке"""
        try:
            # Создаем цикл событий для этого потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Получаем настройки
            settings = QSettings("RemoteAccess", "Agent")
            relay_server = settings.value("server", "ws://localhost:9001")
            quality = int(settings.value("quality", 60))
            fps = float(settings.value("fps", 30))
            screenshot_interval = 1.0 / fps if fps > 0 else 0.05
            
            # Создаем поток агента (без GUI)
            from agent.remote_agent import RemoteAgentThread
            
            self.agent_instance = RemoteAgentThread(
                relay_server=relay_server,
                computer_data=self.computer_data,
                screenshot_interval=screenshot_interval,
                quality=quality
            )
            
            # Настраиваем колбэки для логирования
            self.agent_instance.log_message.connect(self._on_agent_log)
            self.agent_instance.connection_status_changed.connect(self._on_agent_status)
            
            # Запускаем агента (блокирующий вызов)
            self.agent_instance.run()
            
        except Exception as e:
            print(f"[BACKGROUND] Ошибка запуска агента: {e}")
        finally:
            if self.agent_instance:
                self.agent_instance.stop()
            self.running = False
    
    def _on_agent_log(self, message: str):
        """Обработчик логов агента"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[AGENT][{timestamp}] {message}")
    
    def _on_agent_status(self, is_connected: bool, clients_count: int):
        """Обработчик изменения статуса агента"""
        status = "подключен" if is_connected else "отключен"
        print(f"[BACKGROUND] Агент {status}, клиентов: {clients_count}")
    
    def stop(self):
        """Останавливает агента"""
        print("[BACKGROUND] Остановка агента...")
        self.running = False
        if self.agent_instance:
            self.agent_instance.stop()
        if self.agent_thread and self.agent_thread.is_alive():
            self.agent_thread.join(timeout=5)
        print("[BACKGROUND] Агент остановлен")


def run_background_agent(computer_data):
    """Запускает полноценного агента в фоне (для админа)"""
    service = AgentBackgroundService(computer_data)
    service.start()
    return service


def main():
    # Проверка: если приложение уже запущено, показываем сообщение и выходим
    mutex_name = "PC-RMDS-Host-SingleInstance-Mutex"
    mutex = None
    lock_file = None
    
    if sys.platform == 'win32':
        try:
            import ctypes.wintypes
            from ctypes import windll
            
            # Пытаемся создать именованный мьютекс
            mutex = windll.kernel32.CreateMutexW(None, True, mutex_name)
            if not mutex:
                print("Ошибка создания мьютекса")
                sys.exit(1)
            
            error_code = ctypes.get_last_error()
            if error_code == 183:  # ERROR_ALREADY_EXISTS
                print("Приложение уже запущено!")
                QMessageBox.warning(
                    None,
                    "Приложение уже запущено",
                    "Приложение PC-RMDS Host уже запущено.\n\n"
                    "Нельзя запустить несколько копий одновременно.\n"
                    "Если вы хотите открыть новое окно, закройте существующее."
                )
                sys.exit(0)
                
        except Exception as e:
            print(f"Ошибка проверки мьютекса: {e}")
            # Продолжаем работу, если не удалось проверить мьютекс
    else:
        # Для Linux/macOS используем file-based lock
        try:
            import fcntl
            import tempfile
            
            lock_file_path = os.path.join(tempfile.gettempdir(), "pc-rmds-host.lock")
            lock_file = open(lock_file_path, 'w')
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Сохраняем ссылку на файл, чтобы мьютекс не освободился
        except IOError:
            print("Приложение уже запущено!")
            QMessageBox.warning(
                None,
                "Приложение уже запущено",
                "Приложение PC-RMDS Host уже запущено.\n\n"
                "Нельзя запустить несколько копий одновременно.\n"
                "Если вы хотите открыть новое окно, закройте существующее."
            )
            sys.exit(0)
        except Exception as e:
            print(f"Ошибка блокировки: {e}")
    
    # Обеспечиваем создание всех необходимых директорий
    try:
        ensure_dirs()
        print(f"Платформа: {get_platform_name()}")
        print(f"Директория данных: {get_data_dir()}")
    except Exception as e:
        print(f"Ошибка инициализации: {e}")
    
    # Проверяем зависимости при запуске
    try:
        DependencyChecker.print_check_results()
    except Exception as e:
        print(f"Ошибка проверки зависимостей: {e}")
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Remote Access Agent")
    
    # Глобальные переменные для ресурсов
    background_agent_service = None
    admin_window = None
    
    # Обработчик корректного завершения работы
    def on_application_quit():
        nonlocal background_agent_service, admin_window
        print("\n[MAIN] Завершение работы, закрываем сессию...")
        
        # Останавливаем фонового агента
        if background_agent_service:
            print("[MAIN] Остановка фонового агента...")
            background_agent_service.stop()
        
        # Закрываем окно админа если открыто
        if admin_window:
            try:
                admin_window.close_session()
                admin_window.stop_agent()
            except:
                pass
        
        # Закрываем активную сессию
        if APIClient.current_session_id:
            try:
                if APIClient.close_session():
                    print(f"[MAIN] ✅ Сессия {APIClient.current_session_id} успешно закрыта")
            except Exception as e:
                print(f"[MAIN] ❌ Ошибка закрытия сессии: {e}")
        
        # Выполняем выход из системы
        if APIClient.auth_token:
            try:
                APIClient.logout()
                print("[MAIN] ✅ Выполнен выход из системы")
            except Exception as e:
                print(f"[MAIN] ❌ Ошибка выхода: {e}")
        
        # Очищаем мьютекс
        if sys.platform == 'win32' and mutex:
            try:
                from ctypes import windll
                windll.kernel32.ReleaseMutex(mutex)
                windll.kernel32.CloseHandle(mutex)
            except:
                pass
        else:
            try:
                if lock_file:
                    import fcntl
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
                    lock_file.close()
            except:
                pass
    
    # Защита от двойного вызова завершения
    quit_called = False
    
    def on_application_quit_safe():
        nonlocal quit_called
        if quit_called:
            return
        quit_called = True
        on_application_quit()
    
    # Используем сигнал Qt (гарантированно вызывается всегда)
    app.aboutToQuit.connect(on_application_quit_safe)
    
    # Регистрируем также на случай аварийного завершения
    import atexit
    atexit.register(on_application_quit_safe)
    
    # Показываем диалог авторизации
    auth_dialog = AuthDialog()
    if auth_dialog.exec() == AuthDialog.DialogCode.Accepted:
        computer_data = auth_dialog.computer_data
        
        # Создаем сессию при успешном входе
        session_id = APIClient.create_session(computer_data['computer_id'], computer_data.get('user_id'))
        if session_id:
            computer_data['session_id'] = session_id
            computer_data['session_token'] = APIClient.auth_token
            print(f"[MAIN] Сессия создана успешно, ID: {session_id}")
        
        # Проверяем, является ли пользователь админом
        role_id = computer_data.get('role_id', 1)
        is_admin = role_id in (2, 3) or str(role_id) in ('2', '3')
        
        if is_admin:
            # Админ - запускаем полноценного агента в фоне и окно админа
            print(f"👑 Администратор {computer_data.get('login')} вошел в систему")
            print("[MAIN] Запуск полноценного агента в фоновом режиме...")
            
            # Запускаем фонового агента (полный функционал)
            background_agent_service = run_background_agent(computer_data)
            
            # Небольшая задержка для инициализации агента
            import time
            time.sleep(1)
            
            # Показываем панель администратора
            try:
                # Импортируем обновленный AdminPanelWindow
                from admin.admin_panel import AdminPanelWindow
                
                # Получаем настройки сервера
                settings = QSettings("RemoteAccess", "Agent")
                relay_server = settings.value("server", "ws://localhost:9001")
                
                admin_window = AdminPanelWindow(computer_data, relay_server)
                admin_window.show()
                
                # Сохраняем ссылку для остановки
                admin_window.background_agent = background_agent_service
                
                print("[MAIN] Панель администратора запущена, агент работает в фоне")
                sys.exit(app.exec())
                
            except ImportError as e:
                print(f"❌ Ошибка импорта панели администратора: {e}")
                QMessageBox.warning(
                    None,
                    "Предупреждение",
                    f"Панель администратора недоступна.\n"
                    f"Будет запущено клиентское окно.\n\n"
                    f"Ошибка: {e}"
                )
                # Если панель не найдена, запускаем обычное окно агента
                window = RemoteAgentWindow(computer_data)
                window.show()
                sys.exit(app.exec())
                
            except Exception as e:
                print(f"❌ Ошибка запуска панели администратора: {e}")
                import traceback
                traceback.print_exc()
                
                QMessageBox.warning(
                    None,
                    "Ошибка",
                    f"Не удалось запустить панель администратора.\n"
                    f"Ошибка: {e}\n\n"
                    f"Агент продолжает работать в фоновом режиме,\n"
                    f"но панель управления не будет доступна."
                )
                
                # Агент продолжает работать, но панель не показана
                # Ждем завершения
                try:
                    while True:
                        import time
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
        else:
            # Клиент - запускаем обычное окно агента
            print(f"🖥️ Клиент {computer_data.get('login')} вошел в систему")
            window = RemoteAgentWindow(computer_data)
            window.show()
            sys.exit(app.exec())
    else:
        on_application_quit()
        sys.exit(0)


if __name__ == "__main__":
    main()