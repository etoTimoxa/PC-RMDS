import sys
import os
from pathlib import Path
import threading
import multiprocessing

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication, QMessageBox

from agent.auth_dialog import AuthDialog
from agent.remote_agent import RemoteAgentWindow
from agent.admin_panel import AdminPanelWindow
from utils.dependencies import DependencyChecker
from utils.platform_utils import ensure_dirs, get_platform_name, get_data_dir


def run_background_session(computer_data):
    """Запускает сессию в фоновом режиме (для админа)"""
    from core.api_client import APIClient as DatabaseManager
    import time
    
    print(f"[BACKGROUND] Админ {computer_data['login']} запустил фоновую сессию")
    
    try:
        while True:
            # Обновляем активность компьютера
            if computer_data.get('computer_id'):
                DatabaseManager.update_computer_status(
                    computer_data['computer_id'], 
                    True, 
                    computer_data.get('session_id')
                )
            time.sleep(60)  # Обновляем каждые 60 секунд
    except Exception as e:
        print(f"[BACKGROUND] Ошибка фоновой сессии: {e}")


def main():
    # Проверка: если приложение уже запущено, показываем сообщение и выходим
    mutex_name = "PC-RMDS-Host-SingleInstance-Mutex"
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
        import fcntl
        import tempfile
        
        lock_file_path = os.path.join(tempfile.gettempdir(), "pc-rmds-host.lock")
        try:
            lock_file = open(lock_file_path, 'w')
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Сохраняем ссылку на файл, чтобы мьютекс не освободился
            main.lock_file = lock_file
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
    
    # Устанавливаем обработчик для очистки мьютекса при выходе
    def cleanup_mutex():
        if sys.platform == 'win32':
            try:
                from ctypes import windll
                windll.kernel32.ReleaseMutex(mutex)
                windll.kernel32.CloseHandle(mutex)
            except:
                pass
        else:
            try:
                import fcntl
                if hasattr(main, 'lock_file'):
                    fcntl.flock(main.lock_file, fcntl.LOCK_UN)
                    main.lock_file.close()
            except:
                pass
    
    import atexit
    atexit.register(cleanup_mutex)
    
    auth_dialog = AuthDialog()
    if auth_dialog.exec() == AuthDialog.DialogCode.Accepted:
        computer_data = auth_dialog.computer_data
        
        # Проверяем, является ли пользователь админом
        is_admin = computer_data.get('is_admin') or computer_data.get('role_id') in (2, 3)
        
        if is_admin:
            # Админ - запускаем фоновую сессию и окно админа
            print(f"Администратор {computer_data['login']} вошел в систему")
            
            # Запускаем фоновый поток для сессии
            bg_thread = threading.Thread(
                target=run_background_session,
                args=(computer_data,),
                daemon=True
            )
            bg_thread.start()
            
            # Показываем панель администратора
            try:
                admin_window = AdminPanelWindow(computer_data)
                admin_window.show()
                sys.exit(app.exec())
            except Exception as e:
                print(f"Ошибка запуска панели администратора: {e}")
                # Если панель админа не найдена, показываем клиентское окно
                QMessageBox.warning(
                    None,
                    "Предупреждение",
                    f"Панель администратора недоступна.\n"
                    f"Будет запущено клиентское окно.\n\n"
                    f"Ошибка: {e}"
                )
                window = RemoteAgentWindow(computer_data)
                window.show()
                sys.exit(app.exec())
        else:
            # Клиент - запускаем обычное окно
            window = RemoteAgentWindow(computer_data)
            window.show()
            sys.exit(app.exec())
    else:
        cleanup_mutex()
        sys.exit(0)


if __name__ == "__main__":
    main()
