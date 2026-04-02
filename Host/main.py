import sys
import os
from pathlib import Path
import threading
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication, QMessageBox

from agent.auth_dialog import AuthDialog
from agent.remote_agent import RemoteAgentWindow
from agent.admin_panel import AdminPanelWindow
from utils.dependencies import DependencyChecker
from utils.platform_utils import ensure_dirs, get_platform_name, get_data_dir


def run_background_session(computer_data):
    """Запускает сессию в фоновом режиме (для админа)"""
    from core.database_manager import DatabaseManager
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
        sys.exit(0)


if __name__ == "__main__":
    main()
